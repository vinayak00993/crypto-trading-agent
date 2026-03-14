"""
Fear & Greed Contrarian Strategy

Uses the free alternative.me API to get the Crypto Fear & Greed Index.
Classic contrarian approach: "Be greedy when others are fearful."

Signals:
  - BUY when index < 20 (Extreme Fear)
  - SELL when index > 75 (Extreme Greed)
  - HOLD otherwise

Data source: https://api.alternative.me/fng/ (free, no API key needed)
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation

log = structlog.get_logger()


class FearGreedStrategy(BaseStrategy):
    name = "fear_greed"
    required_history = 10  # minimal, we use external API

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        self.fear_threshold = params.get("fear_threshold", 20)
        self.greed_threshold = params.get("greed_threshold", 75)
        self._cached_value: int | None = None
        self._cached_at: float = 0
        self._cache_ttl = 300  # refresh every 5 minutes

    def _fetch_index(self) -> int | None:
        """Fetch Fear & Greed Index from alternative.me (free API)."""
        now = time.time()
        if self._cached_value is not None and (now - self._cached_at) < self._cache_ttl:
            return self._cached_value

        try:
            import urllib.request
            import json

            url = "https://api.alternative.me/fng/?limit=1&format=json"
            req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                value = int(data["data"][0]["value"])
                classification = data["data"][0]["value_classification"]

                self._cached_value = value
                self._cached_at = now

                log.info("fear_greed.fetched", value=value, classification=classification)
                return value
        except Exception as e:
            log.warning("fear_greed.fetch_failed", error=str(e))
            return self._cached_value  # return stale cache if available

    def evaluate(self, pair: str, candles: Any) -> TradeRecommendation:
        fg_value = self._fetch_index()

        if fg_value is None:
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=0.0,
                reason="Fear & Greed data unavailable",
            )

        if fg_value <= self.fear_threshold:
            confidence = min(1.0, (self.fear_threshold - fg_value) / self.fear_threshold + 0.5)
            return TradeRecommendation(
                pair=pair, signal=Signal.BUY, confidence=confidence,
                reason=f"Extreme Fear: F&G={fg_value} (threshold: <{self.fear_threshold})",
                metadata={"fg_value": fg_value, "classification": "Extreme Fear"},
            )

        elif fg_value >= self.greed_threshold:
            confidence = min(1.0, (fg_value - self.greed_threshold) / (100 - self.greed_threshold) + 0.5)
            return TradeRecommendation(
                pair=pair, signal=Signal.SELL, confidence=confidence,
                reason=f"Extreme Greed: F&G={fg_value} (threshold: >{self.greed_threshold})",
                metadata={"fg_value": fg_value, "classification": "Extreme Greed"},
            )

        else:
            zone = "Fear" if fg_value < 40 else "Neutral" if fg_value < 60 else "Greed"
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=0.3,
                reason=f"F&G={fg_value} ({zone}), waiting for extreme",
                metadata={"fg_value": fg_value, "classification": zone},
            )
