"""
DCA Baseline Strategy — Dollar Cost Averaging benchmark.

Buys a fixed amount at regular intervals regardless of price.
This is the "just keep buying" approach — the benchmark that every
other strategy needs to beat to justify its complexity.

No signals, no analysis. Just consistent accumulation.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation


class DCABaselineStrategy(BaseStrategy):
    name = "dca_baseline"
    required_history = 5

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        self.buy_every_n = params.get("dca_interval", 20)  # buy every 20 ticks (~10 min at 30s ticks)
        self._tick_count = 0
        self._positions_open: dict[str, bool] = {}  # track if we hold each pair

    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        if len(candles) < self.required_history:
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=0.0,
                reason=f"Need {self.required_history} candles, have {len(candles)}",
            )

        self._tick_count += 1
        price = candles["close"].iloc[-1]

        # Simple DCA: buy every N ticks if we don't already hold this pair
        if not self._positions_open.get(pair, False):
            if self._tick_count % self.buy_every_n == 0:
                self._positions_open[pair] = True
                return TradeRecommendation(
                    pair=pair, signal=Signal.BUY, confidence=0.6,
                    reason=f"DCA buy #{self._tick_count // self.buy_every_n} at ${price:,.2f}",
                    metadata={"tick": self._tick_count, "price": round(price, 2), "dca_round": self._tick_count // self.buy_every_n},
                )

        # If we hold a position, sell after 2x the buy interval (take profit or rotate)
        elif self._positions_open.get(pair, False):
            if self._tick_count % (self.buy_every_n * 2) == 0:
                self._positions_open[pair] = False
                return TradeRecommendation(
                    pair=pair, signal=Signal.SELL, confidence=0.6,
                    reason=f"DCA rotation sell at ${price:,.2f}",
                    metadata={"tick": self._tick_count, "price": round(price, 2)},
                )

        return TradeRecommendation(
            pair=pair, signal=Signal.HOLD, confidence=0.3,
            reason=f"DCA waiting (tick {self._tick_count}, next buy at {self.buy_every_n - (self._tick_count % self.buy_every_n)})",
            metadata={"tick": self._tick_count, "price": round(price, 2)},
        )
