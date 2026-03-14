"""
SMA Crossover Strategy — the classic moving-average crossover.

Generates a BUY signal when the fast SMA crosses above the slow SMA,
and a SELL signal when the fast SMA crosses below the slow SMA.

This is a simple trend-following strategy. It won't make you rich, but
it's a solid starting point to validate that the whole pipeline works.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation


class SMACrossoverStrategy(BaseStrategy):
    """
    Simple Moving Average crossover strategy.

    Config params:
        fast_period (int): Number of candles for the fast SMA. Default 10.
        slow_period (int): Number of candles for the slow SMA. Default 30.
    """

    @property
    def name(self) -> str:
        return "sma_crossover"

    @property
    def required_history(self) -> int:
        return self.params.get("slow_period", 30) + 5  # a few extra for safety

    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        fast_period = self.params.get("fast_period", 10)
        slow_period = self.params.get("slow_period", 30)

        if len(candles) < slow_period + 2:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.HOLD,
                confidence=0.0,
                reason=f"Not enough data: have {len(candles)} candles, need {slow_period + 2}",
                metadata={},
            )

        # Calculate SMAs
        candles = candles.copy()
        candles["sma_fast"] = candles["close"].rolling(window=fast_period).mean()
        candles["sma_slow"] = candles["close"].rolling(window=slow_period).mean()

        # Get the last two data points to detect a crossover
        current = candles.iloc[-1]
        previous = candles.iloc[-2]

        fast_now = current["sma_fast"]
        slow_now = current["sma_slow"]
        fast_prev = previous["sma_fast"]
        slow_prev = previous["sma_slow"]
        price_now = current["close"]

        metadata: dict[str, Any] = {
            "sma_fast": round(fast_now, 2),
            "sma_slow": round(slow_now, 2),
            "price": round(price_now, 2),
            "fast_period": fast_period,
            "slow_period": slow_period,
        }

        # Bullish crossover: fast crosses above slow
        if fast_prev <= slow_prev and fast_now > slow_now:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.BUY,
                confidence=0.7,
                reason=f"SMA bullish crossover: fast({fast_period})={fast_now:.2f} crossed above slow({slow_period})={slow_now:.2f}",
                metadata=metadata,
            )

        # Bearish crossover: fast crosses below slow
        if fast_prev >= slow_prev and fast_now < slow_now:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.SELL,
                confidence=0.7,
                reason=f"SMA bearish crossover: fast({fast_period})={fast_now:.2f} crossed below slow({slow_period})={slow_now:.2f}",
                metadata=metadata,
            )

        # No crossover — hold
        gap_pct = ((fast_now - slow_now) / slow_now) * 100 if slow_now else 0
        trend = "bullish" if fast_now > slow_now else "bearish"

        return TradeRecommendation(
            pair=pair,
            signal=Signal.HOLD,
            confidence=0.5,
            reason=f"No crossover. Trend: {trend}, SMA gap: {gap_pct:.2f}%",
            metadata=metadata,
        )
