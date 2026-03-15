"""
Network Activity Strategy

Monitors Bitcoin on-chain metrics via free blockchain.com API:
  - Active addresses (unique senders + receivers)
  - Transaction count
  - Compute power

When network activity surges above its moving average, it signals
growing adoption/demand → BUY. When it drops, demand is fading → SELL.

Data source: https://api.blockchain.info/charts/ (free, no key needed)
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation

log = structlog.get_logger()


class NetworkActivityStrategy(BaseStrategy):
    name = "network_activity"
    required_history = 10

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        self.surge_threshold = params.get("surge_threshold", 1.15)   # 15% above average = bullish
        self.drop_threshold = params.get("drop_threshold", 0.85)     # 15% below average = bearish
        self._cached_data: dict | None = None
        self._cached_at: float = 0
        self._cache_ttl = 600  # refresh every 10 minutes

    def _fetch_metrics(self) -> dict | None:
        """Fetch on-chain metrics from blockchain.com (free)."""
        now = time.time()
        if self._cached_data is not None and (now - self._cached_at) < self._cache_ttl:
            return self._cached_data

        try:
            import urllib.request
            import json

            metrics = {}

            # Active addresses (last 30 days)
            url = "https://api.blockchain.info/charts/n-unique-addresses?timespan=30days&format=json"
            req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                values = [p["y"] for p in data.get("values", [])]
                if values:
                    metrics["active_addresses_current"] = values[-1]
                    metrics["active_addresses_avg"] = sum(values) / len(values)
                    metrics["active_addresses_ratio"] = values[-1] / (sum(values) / len(values))

            # Transaction count (last 30 days)
            url = "https://api.blockchain.info/charts/n-transactions?timespan=30days&format=json"
            req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                values = [p["y"] for p in data.get("values", [])]
                if values:
                    metrics["tx_count_current"] = values[-1]
                    metrics["tx_count_avg"] = sum(values) / len(values)
                    metrics["tx_count_ratio"] = values[-1] / (sum(values) / len(values))

            # Compute power (last 30 days)
            url = "https://api.blockchain.info/charts/difficulty?timespan=30days&format=json"
            req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                values = [p["y"] for p in data.get("values", [])]
                if values:
                    metrics["compute_power_current"] = values[-1]
                    metrics["compute_power_avg"] = sum(values) / len(values)
                    metrics["compute_power_ratio"] = values[-1] / (sum(values) / len(values))

            self._cached_data = metrics
            self._cached_at = now

            log.info(
                "network_activity.fetched",
                addr_ratio=round(metrics.get("active_addresses_ratio", 0), 3),
                tx_ratio=round(metrics.get("tx_count_ratio", 0), 3),
                compute_ratio=round(metrics.get("compute_power_ratio", 0), 3),
            )
            return metrics

        except Exception as e:
            log.warning("network_activity.fetch_failed", error=str(e))
            return self._cached_data

    def evaluate(self, pair: str, candles: Any) -> TradeRecommendation:
        # This strategy is BTC-specific; for non-BTC pairs, just follow BTC signal
        metrics = self._fetch_metrics()

        if not metrics:
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=0.0,
                reason="Network data unavailable",
            )

        # Score each metric: +1 for bullish, -1 for bearish, 0 for neutral
        score = 0
        signals = []

        addr_ratio = metrics.get("active_addresses_ratio", 1.0)
        if addr_ratio >= self.surge_threshold:
            score += 1
            signals.append(f"Addresses surging ({addr_ratio:.2f}x avg)")
        elif addr_ratio <= self.drop_threshold:
            score -= 1
            signals.append(f"Addresses dropping ({addr_ratio:.2f}x avg)")

        tx_ratio = metrics.get("tx_count_ratio", 1.0)
        if tx_ratio >= self.surge_threshold:
            score += 1
            signals.append(f"Transactions surging ({tx_ratio:.2f}x avg)")
        elif tx_ratio <= self.drop_threshold:
            score -= 1
            signals.append(f"Transactions dropping ({tx_ratio:.2f}x avg)")

        compute_ratio = metrics.get("compute_power_ratio", 1.0)
        if compute_ratio >= self.surge_threshold:
            score += 1
            signals.append(f"Compute power surging ({compute_ratio:.2f}x avg)")
        elif compute_ratio <= self.drop_threshold:
            score -= 1
            signals.append(f"Compute power dropping ({compute_ratio:.2f}x avg)")

        reason_str = "; ".join(signals) if signals else f"Network stable (addr:{addr_ratio:.2f}x, tx:{tx_ratio:.2f}x, hp:{compute_ratio:.2f}x)"

        if score >= 2:
            return TradeRecommendation(
                pair=pair, signal=Signal.BUY, confidence=0.7,
                reason=f"Network bullish ({score}/3): {reason_str}",
                metadata=metrics,
            )
        elif score <= -2:
            return TradeRecommendation(
                pair=pair, signal=Signal.SELL, confidence=0.7,
                reason=f"Network bearish ({score}/3): {reason_str}",
                metadata=metrics,
            )
        else:
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=0.3,
                reason=f"Network mixed ({score}/3): {reason_str}",
                metadata=metrics,
            )
