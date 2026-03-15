"""
ML Meta-Learner v2 — Persistent, Learning, Autonomous

Upgrades over v1:
  1. PERSISTENT MEMORY: Saves all learned data to disk. Survives restarts.
  2. REAL ML MODEL: Gradient boosting that learns signal COMBINATIONS,
     not just individual pod accuracy. Discovers patterns like
     "RSI + Fear&Greed together predict better than either alone."
  3. EXTERNAL DATA FEEDS: Funding rates, liquidation data, and market
     context that no other pod sees.

Learning cycle:
  COLD START (< 200 samples): Use weighted voting (same as v1)
  WARM (200-500 samples): Train initial ML model, use with caution
  HOT (500+ samples): Full ML model with high confidence

The model retrains every 50 ticks on the latest data.
All state persists to disk — restart the agent and it picks up where it left off.

v2.1 changes:
  - Atomic file writes (write to .tmp, then rename) to prevent data
    corruption during Railway container restarts/redeploys.
  - Automatic fallback to .bak backup if primary file is corrupted.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation

log = structlog.get_logger()

# Persistent storage path
DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "ml_learner"


# ---------------------------------------------------------------------------
# External data fetchers (all free, no API key needed)
# ---------------------------------------------------------------------------
class ExternalData:
    """Fetches market context data from free APIs."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._cache_times: dict[str, float] = {}
        self._cache_ttl = 300  # 5 min cache

    def _fetch_json(self, url: str, key: str) -> Any:
        """Cached JSON fetch."""
        now = time.time()
        if key in self._cache and (now - self._cache_times.get(key, 0)) < self._cache_ttl:
            return self._cache[key]

        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/2.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                self._cache[key] = data
                self._cache_times[key] = now
                return data
        except Exception as e:
            log.debug("external_data.fetch_failed", key=key, error=str(e))
            return self._cache.get(key)

    def get_fear_greed(self) -> dict:
        """Fear & Greed Index (0-100)."""
        data = self._fetch_json(
            "https://api.alternative.me/fng/?limit=1&format=json", "fng"
        )
        if data and "data" in data:
            return {
                "fg_value": int(data["data"][0]["value"]),
                "fg_class": data["data"][0]["value_classification"],
            }
        return {"fg_value": 50, "fg_class": "Neutral"}

    def get_funding_rates(self) -> dict:
        """BTC funding rate from CoinGlass (free endpoint)."""
        try:
            data = self._fetch_json(
                "https://open-api.coinglass.com/public/v2/funding?symbol=BTC&time_type=all",
                "funding"
            )
            if data and data.get("data"):
                # Get average funding rate across exchanges
                rates = []
                for item in data["data"][:5]:
                    rate = item.get("rate", 0) or item.get("currentFundingRate", 0)
                    if rate:
                        rates.append(float(rate))
                avg_rate = sum(rates) / len(rates) if rates else 0
                return {"funding_rate": avg_rate, "num_exchanges": len(rates)}
        except Exception:
            pass
        return {"funding_rate": 0.0, "num_exchanges": 0}

    def get_btc_dominance(self) -> dict:
        """BTC market dominance."""
        data = self._fetch_json(
            "https://api.alternative.me/v2/ticker/bitcoin/?convert=USD", "btc_dom"
        )
        if data and "data" in data:
            btc_data = data["data"].get("1", {})
            quotes = btc_data.get("quotes", {}).get("USD", {})
            return {
                "btc_dominance": quotes.get("market_cap_dominance", 50),
                "btc_24h_change": quotes.get("percent_change_24h", 0),
                "btc_7d_change": quotes.get("percent_change_7d", 0),
            }
        return {"btc_dominance": 50, "btc_24h_change": 0, "btc_7d_change": 0}

    def get_all(self) -> dict:
        """Fetch all external data as a flat dict of features."""
        features = {}
        features.update(self.get_fear_greed())
        features.update(self.get_funding_rates())
        features.update(self.get_btc_dominance())
        return features


# Override ExternalData with expanded v3 (Binance, CoinGecko, S&P 500, etc.)
from agent.strategies.external_feeds import ExternalData


# ---------------------------------------------------------------------------
# Persistent storage (v2.1 — atomic writes with backup recovery)
# ---------------------------------------------------------------------------
class PersistentMemory:
    """
    Saves and loads ML learner state to/from disk.

    Uses atomic writes (write to .tmp, rename to final) so that if the
    Railway container is killed mid-write during a redeploy, the file
    is never left half-written. Falls back to .bak if the primary file
    is corrupted.
    """

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, filename: str, data: Any) -> None:
        """Write JSON data atomically: write to .tmp, then rename."""
        path = self.data_dir / filename
        tmp_path = self.data_dir / f"{filename}.tmp"
        bak_path = self.data_dir / f"{filename}.bak"

        try:
            # Step 1: Write to temp file
            with open(tmp_path, "w") as f:
                json.dump(data, f, default=str)

            # Step 2: Backup current file (if it exists and is valid)
            if path.exists():
                try:
                    bak_path.unlink(missing_ok=True)
                    path.rename(bak_path)
                except OSError as e:
                    log.debug("ml.backup_failed", file=filename, error=str(e))

            # Step 3: Atomic rename (on same filesystem, this is atomic on Linux)
            tmp_path.rename(path)

        except Exception as e:
            log.warning("ml.atomic_write_failed", file=filename, error=str(e))
            # Clean up temp file if it exists
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _safe_read(self, filename: str) -> Any | None:
        """Read JSON with fallback to .bak if primary is corrupted."""
        path = self.data_dir / filename
        bak_path = self.data_dir / f"{filename}.bak"

        for source in [path, bak_path]:
            if source.exists():
                try:
                    with open(source) as f:
                        data = json.load(f)
                    if source == bak_path:
                        log.warning("ml.using_backup", file=filename)
                    return data
                except (json.JSONDecodeError, ValueError) as e:
                    log.warning("ml.corrupt_file", file=source.name, error=str(e))

        return None

    def save_training_data(self, samples: list[dict]) -> None:
        # Keep last 5000 samples
        samples = samples[-5000:]
        self._atomic_write("training_samples.json", samples)
        log.debug("ml.memory_saved", samples=len(samples))

    def load_training_data(self) -> list[dict]:
        data = self._safe_read("training_samples.json")
        if data is not None and isinstance(data, list):
            log.info("ml.memory_loaded", samples=len(data))
            return data
        if data is None:
            log.info("ml.no_previous_data")
        else:
            log.warning("ml.corrupt_data_reset")
        return []

    def save_pod_stats(self, stats: dict) -> None:
        self._atomic_write("pod_stats.json", stats)

    def load_pod_stats(self) -> dict:
        data = self._safe_read("pod_stats.json")
        return data if isinstance(data, dict) else {}

    def save_model_meta(self, meta: dict) -> None:
        self._atomic_write("model_meta.json", meta)

    def load_model_meta(self) -> dict:
        data = self._safe_read("model_meta.json")
        return data if isinstance(data, dict) else {"total_ticks": 0, "total_trades": 0, "model_version": 0}


# ---------------------------------------------------------------------------
# ML Model wrapper
# ---------------------------------------------------------------------------
class SignalModel:
    """
    Gradient Boosting model that learns from pod signals + external data.

    Features per sample:
      - 8 pod signals (encoded as: BUY=1, HOLD=0, SELL=-1)
      - 8 pod confidences
      - 8 pod rolling accuracies
      - Fear & Greed value
      - Funding rate
      - BTC dominance
      - BTC 24h change
      - Price momentum (5-candle change %)

    Target: 1 = price went up after signal, 0 = price went down
    """

    def __init__(self) -> None:
        self.model = None
        self.is_trained = False
        self.feature_names: list[str] = []
        self.train_count = 0
        self.accuracy = 0.0

    def _signal_to_num(self, signal: str) -> float:
        return {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0}.get(signal, 0.0)

    def build_features(
        self,
        pod_signals: dict[str, dict],  # {pod_name: {"signal": "BUY", "confidence": 0.7}}
        pod_accuracies: dict[str, float],
        external: dict,
        price_momentum: float,
    ) -> np.ndarray:
        """Build a feature vector from current state."""
        features = []
        names = []

        # Pod signals and confidences
        pod_order = sorted(pod_signals.keys())
        for pname in pod_order:
            sig_data = pod_signals[pname]
            features.append(self._signal_to_num(sig_data.get("signal", "HOLD")))
            names.append(f"{pname}_signal")
            features.append(sig_data.get("confidence", 0.0))
            names.append(f"{pname}_confidence")
            features.append(pod_accuracies.get(pname, 0.5))
            names.append(f"{pname}_accuracy")

        # External data
        features.append(external.get("fg_value", 50) / 100.0)
        names.append("fear_greed_norm")
        features.append(external.get("funding_rate", 0.0))
        names.append("funding_rate")
        features.append(external.get("btc_dominance", 50) / 100.0)
        names.append("btc_dominance_norm")
        features.append(external.get("btc_24h_change", 0.0) / 10.0)
        names.append("btc_24h_change_norm")
        features.append(external.get("btc_open_interest", 0) / 100000.0)
        names.append("btc_open_interest_norm")
        features.append(external.get("long_short_ratio", 1.0))
        names.append("long_short_ratio")
        features.append(external.get("long_account_pct", 0.5))
        names.append("long_account_pct")
        features.append(external.get("taker_buy_sell_ratio", 1.0))
        names.append("taker_buy_sell_ratio")
        features.append(external.get("market_cap_change_24h", 0) / 5.0)
        names.append("market_cap_change_norm")
        features.append(external.get("sp500_daily_change", 0) / 3.0)
        names.append("sp500_change_norm")
        features.append(external.get("trends_bitcoin", 50) / 100.0)
        names.append("trends_bitcoin_norm")
        features.append(external.get("trends_crash", 0) / 100.0)
        names.append("trends_crash_norm")
        features.append(external.get("trends_buy", 0) / 100.0)
        names.append("trends_buy_norm")
        features.append(price_momentum / 5.0)
        names.append("price_momentum_norm")

        self.feature_names = names
        return np.array(features, dtype=np.float64)

    def train(self, samples: list[dict]) -> bool:
        """Train the model on historical samples."""
        if len(samples) < 200:
            return False

        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.model_selection import cross_val_score

            # Filter out samples with mismatched feature lengths
            expected_len = len(samples[-1]["features"])
            clean = [s for s in samples if len(s.get("features", [])) == expected_len]
            if len(clean) < 200:
                log.info("ml.insufficient_clean_samples", total=len(samples), clean=len(clean))
                return False

            X = np.array([s["features"] for s in clean])
            y = np.array([s["target"] for s in clean])

            # Check we have both classes
            if len(set(y)) < 2:
                return False

            # Train with conservative parameters to avoid overfitting
            self.model = GradientBoostingClassifier(
                n_estimators=50,
                max_depth=3,
                learning_rate=0.05,
                min_samples_leaf=20,
                subsample=0.7,
                max_features=0.8,
                random_state=42,
            )

            # Use 70/30 split for more honest accuracy measurement
            split = int(len(X) * 0.7)
            X_train, X_test = X[:split], X[split:]
            y_train, y_test = y[:split], y[split:]

            self.model.fit(X_train, y_train)
            self.accuracy = self.model.score(X_test, y_test)

            # Reject model if accuracy looks too good (overfitting)
            if self.accuracy > 0.85 and len(clean) < 500:
                log.warning("ml.likely_overfit", accuracy=round(self.accuracy, 3), samples=len(clean))
                self.model = None
                self.is_trained = False
                return False

            self.is_trained = True
            self.train_count = len(samples)

            # Feature importance logging
            if hasattr(self.model, "feature_importances_") and self.feature_names:
                importances = dict(zip(self.feature_names, self.model.feature_importances_))
                top5 = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:5]
                log.info(
                    "ml.model_trained",
                    samples=len(samples),
                    accuracy=round(self.accuracy, 3),
                    top_features=[(name, round(imp, 3)) for name, imp in top5],
                )

            return True

        except ImportError:
            log.warning("ml.sklearn_not_available", msg="Install scikit-learn for ML model")
            return False
        except Exception as e:
            log.warning("ml.train_failed", error=str(e))
            return False

    def predict(self, features: np.ndarray) -> tuple[str, float]:
        """Predict BUY/SELL/HOLD with confidence."""
        if not self.is_trained or self.model is None:
            return "HOLD", 0.0

        try:
            proba = self.model.predict_proba(features.reshape(1, -1))[0]
            classes = self.model.classes_

            # Map to signal
            class_map = {c: p for c, p in zip(classes, proba)}
            buy_prob = class_map.get(1, 0.0)
            sell_prob = class_map.get(0, 0.0)

            if buy_prob > 0.6:
                return "BUY", buy_prob
            elif sell_prob > 0.6:
                return "SELL", sell_prob
            else:
                return "HOLD", max(buy_prob, sell_prob)

        except Exception as e:
            log.debug("ml.predict_failed", error=str(e))
            return "HOLD", 0.0


# ---------------------------------------------------------------------------
# Main strategy
# ---------------------------------------------------------------------------
class MLMetaLearner(BaseStrategy):
    """
    ML Meta-Learner v2 — Persistent, learning, autonomous.

    Observes all other pods, learns signal combinations via gradient boosting,
    incorporates external market data, and persists all knowledge to disk.
    """

    name = "ml_meta_learner"
    required_history = 10

    # Phase thresholds
    COLD_THRESHOLD = 200     # samples needed before ML model kicks in
    WARM_THRESHOLD = 500     # samples for confident trading
    RETRAIN_INTERVAL = 50    # retrain every 50 ticks

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        self.eval_delay = params.get("eval_delay", 20)
        self.min_confidence = params.get("ml_min_confidence", 0.55)

        # Core components
        self.memory = PersistentMemory()
        self.model = SignalModel()
        self.external = ExternalData()

        # State
        self.tick_count = 0
        self.pod_signals: dict[str, dict[str, dict]] = defaultdict(dict)  # {pair: {pod: {signal, conf}}}
        self.pod_accuracies: dict[str, float] = {}
        self.pod_correct: dict[str, int] = defaultdict(int)
        self.pod_total: dict[str, int] = defaultdict(int)
        self._price_history: dict[str, list[tuple[int, float]]] = defaultdict(list)
        self._pending_evals: list[dict] = []
        self._training_samples: list[dict] = []

        # Load persistent state
        self._load_state()

    def _load_state(self) -> None:
        """Restore learned state from disk."""
        self._training_samples = self.memory.load_training_data()
        stats = self.memory.load_pod_stats()
        meta = self.memory.load_model_meta()

        self.tick_count = meta.get("total_ticks", 0)

        # Restore pod accuracies
        for name, data in stats.items():
            self.pod_correct[name] = data.get("correct", 0)
            self.pod_total[name] = data.get("total", 0)
            if self.pod_total[name] > 0:
                self.pod_accuracies[name] = self.pod_correct[name] / self.pod_total[name]

        # Retrain model if we have enough data
        if len(self._training_samples) >= self.COLD_THRESHOLD:
            self.model.train(self._training_samples)

        if self._training_samples:
            log.info(
                "ml.state_restored",
                samples=len(self._training_samples),
                ticks=self.tick_count,
                model_trained=self.model.is_trained,
                model_accuracy=round(self.model.accuracy, 3),
            )

    def _save_state(self) -> None:
        """Persist learned state to disk."""
        self.memory.save_training_data(self._training_samples)

        pod_stats = {}
        for name in set(list(self.pod_correct.keys()) + list(self.pod_total.keys())):
            pod_stats[name] = {
                "correct": self.pod_correct.get(name, 0),
                "total": self.pod_total.get(name, 0),
                "accuracy": round(self.pod_accuracies.get(name, 0.5), 4),
            }
        self.memory.save_pod_stats(pod_stats)

        self.memory.save_model_meta({
            "total_ticks": self.tick_count,
            "total_samples": len(self._training_samples),
            "model_trained": self.model.is_trained,
            "model_accuracy": round(self.model.accuracy, 4),
            "model_version": self.model.train_count,
        })

    @property
    def phase(self) -> str:
        n = len(self._training_samples)
        if n < self.COLD_THRESHOLD:
            return "LEARNING"
        elif n < self.WARM_THRESHOLD:
            return "WARMING"
        return "AUTONOMOUS"

    def record_signal(self, pod_name: str, pair: str, signal: str,
                      confidence: float, price: float, tick: int) -> None:
        """Called by agent loop to feed signals from other pods."""
        self.pod_signals[pair][pod_name] = {
            "signal": signal, "confidence": confidence,
        }

        # Queue BUY/SELL signals for evaluation
        if signal in ("BUY", "SELL"):
            self._pending_evals.append({
                "pod_name": pod_name, "tick": tick,
                "pair": pair, "signal": signal,
                "price_at_signal": price,
                "external": self.external.get_all(),
                "pod_signals_snapshot": {
                    p: dict(s) for p, s in self.pod_signals.get(pair, {}).items()
                },
            })

    def record_price(self, pair: str, price: float, tick: int) -> None:
        self._price_history[pair].append((tick, price))
        if len(self._price_history[pair]) > 1000:
            self._price_history[pair] = self._price_history[pair][-1000:]

    def _get_price_momentum(self, pair: str, lookback: int = 5) -> float:
        """Calculate recent price change %."""
        history = self._price_history.get(pair, [])
        if len(history) < lookback + 1:
            return 0.0
        current = history[-1][1]
        past = history[-(lookback + 1)][1]
        if past == 0:
            return 0.0
        return ((current - past) / past) * 100

    def _evaluate_pending(self) -> None:
        """Check old signals and create training samples."""
        still_pending = []

        for entry in self._pending_evals:
            ticks_elapsed = self.tick_count - entry["tick"]
            if ticks_elapsed < self.eval_delay:
                still_pending.append(entry)
                continue

            # Find price after delay
            pair = entry["pair"]
            target_tick = entry["tick"] + self.eval_delay
            price_after = None
            for tick, price in self._price_history.get(pair, []):
                if tick >= target_tick:
                    price_after = price
                    break

            if price_after is None:
                if ticks_elapsed < self.eval_delay * 3:
                    still_pending.append(entry)
                continue

            price_at = entry["price_at_signal"]
            signal = entry["signal"]
            pod_name = entry["pod_name"]

            # Was the signal correct?
            if signal == "BUY":
                correct = price_after > price_at
                target = 1 if correct else 0
            else:
                correct = price_after < price_at
                target = 0 if correct else 1

            # Update pod accuracy
            self.pod_total[pod_name] = self.pod_total.get(pod_name, 0) + 1
            if correct:
                self.pod_correct[pod_name] = self.pod_correct.get(pod_name, 0) + 1
            total = self.pod_total[pod_name]
            if total > 0:
                self.pod_accuracies[pod_name] = self.pod_correct[pod_name] / total

            # Build training sample
            pod_sigs = entry.get("pod_signals_snapshot", {})
            ext = entry.get("external", {})
            momentum = ((price_at - price_after) / price_at * 100) if price_at else 0

            features = self.model.build_features(
                pod_signals=pod_sigs,
                pod_accuracies=self.pod_accuracies,
                external=ext,
                price_momentum=momentum,
            )

            self._training_samples.append({
                "features": features.tolist(),
                "target": int(target),  # Cast to Python int for JSON serialization
                "tick": entry["tick"],
                "pair": pair,
                "pod": pod_name,
                "signal": signal,
                "correct": bool(correct),  # Cast to Python bool for JSON serialization
            })

        self._pending_evals = still_pending

    def _maybe_retrain(self) -> None:
        """Retrain the model periodically."""
        n = len(self._training_samples)
        if n < self.COLD_THRESHOLD:
            return
        if n % self.RETRAIN_INTERVAL == 0 or (n == self.COLD_THRESHOLD):
            success = self.model.train(self._training_samples)
            if success:
                self._save_state()

    def _weighted_vote(self, pair: str) -> tuple[str, float]:
        """Fallback: weighted voting when ML model isn't ready."""
        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0

        for pod_name, sig_data in self.pod_signals.get(pair, {}).items():
            if pod_name == self.name:
                continue
            acc = self.pod_accuracies.get(pod_name, 0.5)
            weight = max(0.1, min(2.0, acc * 2.0))
            signal = sig_data.get("signal", "HOLD")

            if signal == "BUY":
                buy_score += weight
            elif signal == "SELL":
                sell_score += weight
            total_weight += weight

        if total_weight == 0:
            return "HOLD", 0.0

        buy_pct = buy_score / total_weight
        sell_pct = sell_score / total_weight

        if buy_pct > 0.4 and buy_pct > sell_pct:
            return "BUY", buy_pct
        elif sell_pct > 0.4 and sell_pct > buy_pct:
            return "SELL", sell_pct
        return "HOLD", max(buy_pct, sell_pct)

    def get_pod_rankings(self) -> list[dict]:
        rankings = []
        for name in set(list(self.pod_total.keys())):
            if name == self.name:
                continue
            total = self.pod_total.get(name, 0)
            correct = self.pod_correct.get(name, 0)
            acc = (correct / total * 100) if total > 0 else 50.0
            rankings.append({
                "name": name, "accuracy": round(acc, 1),
                "weight": round(max(0.1, min(2.0, (acc / 100) * 2.0)), 2),
                "evaluated": total,
            })
        return sorted(rankings, key=lambda x: x["accuracy"], reverse=True)

    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        self.tick_count += 1

        # Record price
        if not candles.empty:
            price = candles["close"].iloc[-1]
            self.record_price(pair, price, self.tick_count)

        # Evaluate pending signals
        self._evaluate_pending()

        # Maybe retrain
        self._maybe_retrain()

        # Save state every 25 ticks
        if self.tick_count % 25 == 0:
            self._save_state()

        phase = self.phase
        n_samples = len(self._training_samples)
        rankings = self.get_pod_rankings()
        top_str = ", ".join(f"{r['name']}:{r['accuracy']}%" for r in rankings[:3])

        # Get external context
        ext = self.external.get_all()
        momentum = self._get_price_momentum(pair)

        # Decide: use ML model or weighted voting
        if self.model.is_trained and n_samples >= self.COLD_THRESHOLD:
            # ML MODEL PREDICTION
            current_signals = self.pod_signals.get(pair, {})
            features = self.model.build_features(
                pod_signals=current_signals,
                pod_accuracies=self.pod_accuracies,
                external=ext,
                price_momentum=momentum,
            )
            signal_str, confidence = self.model.predict(features)

            reason = (
                f"{phase} [ML model, acc={self.model.accuracy:.0%}, "
                f"samples={n_samples}] -> {signal_str} "
                f"| F&G={ext.get('fg_value', '?')} "
                f"| Top: {top_str}"
            )

        else:
            # WEIGHTED VOTING (fallback)
            signal_str, confidence = self._weighted_vote(pair)
            remaining = self.COLD_THRESHOLD - n_samples

            reason = (
                f"{phase} [weighted vote, {n_samples}/{self.COLD_THRESHOLD} samples] "
                f"-> {signal_str} "
                f"| F&G={ext.get('fg_value', '?')} "
                f"| Top: {top_str}"
            )

        # Convert to Signal enum
        signal = {"BUY": Signal.BUY, "SELL": Signal.SELL}.get(signal_str, Signal.HOLD)

        # Apply confidence threshold
        if confidence < self.min_confidence:
            signal = Signal.HOLD

        return TradeRecommendation(
            pair=pair, signal=signal, confidence=confidence,
            reason=reason,
            metadata={
                "phase": phase,
                "tick": self.tick_count,
                "samples": n_samples,
                "model_trained": self.model.is_trained,
                "model_accuracy": round(self.model.accuracy, 3),
                "external": ext,
                "rankings": rankings[:5],
            },
        )
