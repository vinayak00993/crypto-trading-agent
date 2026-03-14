"""
ML Meta-Learner Strategy — Pod #9

A live-learning agent that sits on top of all 8 strategy pods.
It observes every signal, tracks which pods are accurate over time,
and makes its own trades using a weighted vote from the best performers.

Learning cycle:
  1. OBSERVE (ticks 1-100): Watch all pods, track signals vs outcomes. No trades.
  2. LEARN (ticks 100-200): Start calculating rolling accuracy. Conservative trades.
  3. ADAPT (ticks 200+): Full autonomous trading with dynamic pod weighting.

The goal: outperform any individual pod by cherry-picking the best signals.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import structlog

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation

log = structlog.get_logger()


@dataclass
class PodRecord:
    """Tracks a single pod's signal history and accuracy."""
    signals: list[dict] = field(default_factory=list)      # [{tick, pair, signal, price}, ...]
    outcomes: list[dict] = field(default_factory=list)      # [{tick, pair, signal, price_at_signal, price_after, correct}, ...]
    correct_count: int = 0
    total_evaluated: int = 0
    cumulative_pnl: float = 0.0

    @property
    def accuracy(self) -> float:
        if self.total_evaluated == 0:
            return 0.5  # no data yet, assume 50/50
        return self.correct_count / self.total_evaluated

    @property
    def weight(self) -> float:
        """Dynamic weight based on accuracy. Range: 0.1 to 2.0"""
        if self.total_evaluated < 10:
            return 1.0  # not enough data, use equal weight
        # Scale accuracy to weight: 50% accuracy = 1.0 weight, 70% = 1.4, 30% = 0.6
        return max(0.1, min(2.0, self.accuracy * 2.0))


class MLMetaLearner(BaseStrategy):
    """
    Meta-learning strategy that learns from all other pods.

    It doesn't analyze price charts directly — instead it:
    1. Collects signals from other pods (fed via record_signal())
    2. Evaluates whether those signals were correct after a delay
    3. Weights each pod by its rolling accuracy
    4. Makes its own trades using the weighted consensus
    """

    name = "ml_meta_learner"
    required_history = 10

    # Phase thresholds
    OBSERVE_PHASE_END = 100    # first 100 ticks: just watch
    LEARN_PHASE_END = 200      # ticks 100-200: conservative trades
    # After 200: full autonomous mode

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        self.tick_count = 0
        self.eval_delay = params.get("eval_delay", 20)  # evaluate signal after 20 ticks (~10 min)
        self.min_confidence = params.get("ml_min_confidence", 0.55)
        self.pods: dict[str, PodRecord] = defaultdict(PodRecord)
        self._price_history: dict[str, list[tuple[int, float]]] = defaultdict(list)  # {pair: [(tick, price), ...]}
        self._pending_evals: list[dict] = []  # signals waiting to be evaluated

    @property
    def phase(self) -> str:
        if self.tick_count < self.OBSERVE_PHASE_END:
            return "OBSERVE"
        elif self.tick_count < self.LEARN_PHASE_END:
            return "LEARN"
        return "ADAPT"

    def record_signal(self, pod_name: str, pair: str, signal: str, price: float, tick: int) -> None:
        """
        Called by the agent loop to feed signals from other pods.
        This is how the meta-learner observes the other strategies.
        """
        record = {
            "tick": tick,
            "pair": pair,
            "signal": signal,
            "price": price,
            "timestamp": time.time(),
        }
        self.pods[pod_name].signals.append(record)

        # Queue for evaluation after delay
        if signal in ("BUY", "SELL"):
            self._pending_evals.append({
                "pod_name": pod_name,
                "tick": tick,
                "pair": pair,
                "signal": signal,
                "price_at_signal": price,
            })

    def record_price(self, pair: str, price: float, tick: int) -> None:
        """Record current price for later signal evaluation."""
        self._price_history[pair].append((tick, price))
        # Keep last 500 price points per pair
        if len(self._price_history[pair]) > 500:
            self._price_history[pair] = self._price_history[pair][-500:]

    def _evaluate_pending_signals(self) -> None:
        """Check if old signals were correct based on price movement after delay."""
        still_pending = []

        for entry in self._pending_evals:
            ticks_elapsed = self.tick_count - entry["tick"]

            if ticks_elapsed < self.eval_delay:
                still_pending.append(entry)
                continue

            # Find the price at eval_delay ticks after the signal
            pair = entry["pair"]
            target_tick = entry["tick"] + self.eval_delay
            price_after = None

            for tick, price in self._price_history[pair]:
                if tick >= target_tick:
                    price_after = price
                    break

            if price_after is None:
                still_pending.append(entry)
                continue

            # Evaluate: was the signal correct?
            price_at = entry["price_at_signal"]
            signal = entry["signal"]

            if signal == "BUY":
                correct = price_after > price_at  # price went up = correct buy
                pnl_pct = ((price_after - price_at) / price_at) * 100
            else:  # SELL
                correct = price_after < price_at  # price went down = correct sell
                pnl_pct = ((price_at - price_after) / price_at) * 100

            pod_record = self.pods[entry["pod_name"]]
            pod_record.total_evaluated += 1
            if correct:
                pod_record.correct_count += 1
            pod_record.cumulative_pnl += pnl_pct

            pod_record.outcomes.append({
                "tick": entry["tick"],
                "pair": pair,
                "signal": signal,
                "price_at_signal": price_at,
                "price_after": price_after,
                "correct": correct,
                "pnl_pct": round(pnl_pct, 3),
            })

            # Keep only last 200 outcomes per pod
            if len(pod_record.outcomes) > 200:
                pod_record.outcomes = pod_record.outcomes[-200:]

        self._pending_evals = still_pending

    def _get_weighted_consensus(self, pair: str) -> tuple[Signal, float, str]:
        """
        Calculate weighted vote across all pods for a given pair.
        Returns (signal, confidence, reason).
        """
        buy_score = 0.0
        sell_score = 0.0
        hold_score = 0.0
        total_weight = 0.0
        voters = []

        for pod_name, pod_record in self.pods.items():
            if pod_name == self.name:
                continue

            # Get this pod's most recent signal for this pair
            recent = None
            for sig in reversed(pod_record.signals):
                if sig["pair"] == pair:
                    recent = sig
                    break

            if recent is None:
                continue

            weight = pod_record.weight
            signal = recent["signal"]

            if signal == "BUY":
                buy_score += weight
            elif signal == "SELL":
                sell_score += weight
            else:
                hold_score += weight

            total_weight += weight
            voters.append(f"{pod_name}({signal[0]},w={weight:.1f})")

        if total_weight == 0:
            return Signal.HOLD, 0.0, "No pod signals available"

        # Normalize scores
        buy_pct = buy_score / total_weight
        sell_pct = sell_score / total_weight

        # Build reason string
        top_pods = sorted(self.pods.items(), key=lambda x: x[1].weight, reverse=True)[:3]
        top_str = ", ".join(f"{n}:{r.accuracy:.0%}" for n, r in top_pods if r.total_evaluated > 0)

        if buy_pct > sell_pct and buy_pct > 0.4:
            confidence = min(1.0, buy_pct)
            return Signal.BUY, confidence, f"Weighted BUY ({buy_pct:.0%}) | Top pods: {top_str}"
        elif sell_pct > buy_pct and sell_pct > 0.4:
            confidence = min(1.0, sell_pct)
            return Signal.SELL, confidence, f"Weighted SELL ({sell_pct:.0%}) | Top pods: {top_str}"
        else:
            return Signal.HOLD, 0.3, f"No consensus (B:{buy_pct:.0%} S:{sell_pct:.0%}) | Top pods: {top_str}"

    def get_pod_rankings(self) -> list[dict]:
        """Return pod rankings for dashboard display."""
        rankings = []
        for name, record in self.pods.items():
            if name == self.name:
                continue
            rankings.append({
                "name": name,
                "accuracy": round(record.accuracy * 100, 1),
                "weight": round(record.weight, 2),
                "evaluated": record.total_evaluated,
                "pnl": round(record.cumulative_pnl, 2),
            })
        return sorted(rankings, key=lambda x: x["weight"], reverse=True)

    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        self.tick_count += 1

        # Record current price for evaluation
        if not candles.empty:
            price = candles["close"].iloc[-1]
            self.record_price(pair, price, self.tick_count)

        # Evaluate pending signals
        self._evaluate_pending_signals()

        phase = self.phase
        rankings = self.get_pod_rankings()
        rankings_str = ", ".join(f"{r['name']}:{r['accuracy']}%" for r in rankings[:3]) if rankings else "none"

        # Phase 1: OBSERVE — just watch, don't trade
        if phase == "OBSERVE":
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=0.0,
                reason=f"OBSERVE phase (tick {self.tick_count}/{self.OBSERVE_PHASE_END}). Learning... Top: {rankings_str}",
                metadata={"phase": phase, "tick": self.tick_count, "rankings": rankings},
            )

        # Phase 2 & 3: LEARN / ADAPT — make weighted trades
        signal, confidence, reason = self._get_weighted_consensus(pair)

        # In LEARN phase, require higher confidence
        if phase == "LEARN":
            min_conf = self.min_confidence + 0.1
            if confidence < min_conf:
                return TradeRecommendation(
                    pair=pair, signal=Signal.HOLD, confidence=confidence,
                    reason=f"LEARN phase: {reason} (need {min_conf:.0%} conf, have {confidence:.0%})",
                    metadata={"phase": phase, "tick": self.tick_count, "rankings": rankings},
                )

        # In ADAPT phase, use standard confidence threshold
        if confidence < self.min_confidence:
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=confidence,
                reason=f"{phase}: {reason} (below {self.min_confidence:.0%} threshold)",
                metadata={"phase": phase, "tick": self.tick_count, "rankings": rankings},
            )

        return TradeRecommendation(
            pair=pair, signal=signal, confidence=confidence,
            reason=f"{phase}: {reason}",
            metadata={"phase": phase, "tick": self.tick_count, "rankings": rankings},
        )
