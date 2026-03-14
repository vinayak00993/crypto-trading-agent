"""
MACD (Moving Average Convergence Divergence) Strategy.

MACD measures the relationship between two exponential moving averages.
When the MACD line crosses above the signal line → bullish (BUY).
When it crosses below → bearish (SELL).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation


class MACDStrategy(BaseStrategy):
    """
    MACD crossover strategy.

    Config params:
        fast_period (int): Fast EMA period. Default 12.
        slow_period (int): Slow EMA period. Default 26.
        signal_period (int): Signal line EMA period. Default 9.
    """

    @property
    def name(self) -> str:
        return "macd"

    @property
    def required_history(self) -> int:
        return self.params.get("slow_period", 26) + self.params.get("signal_period", 9) + 5

    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        fast = self.params.get("fast_period", 12)
        slow = self.params.get("slow_period", 26)
        signal_period = self.params.get("signal_period", 9)

        min_needed = slow + signal_period + 2
        if len(candles) < min_needed:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.HOLD,
                confidence=0.0,
                reason=f"Not enough data: have {len(candles)}, need {min_needed}",
                metadata={},
            )

        close = candles["close"]

        # Calculate MACD components
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        macd_now = float(macd_line.iloc[-1])
        macd_prev = float(macd_line.iloc[-2])
        signal_now = float(signal_line.iloc[-1])
        signal_prev = float(signal_line.iloc[-2])
        hist_now = float(histogram.iloc[-1])
        price = float(close.iloc[-1])

        metadata: dict[str, Any] = {
            "macd": round(macd_now, 4),
            "signal": round(signal_now, 4),
            "histogram": round(hist_now, 4),
            "price": round(price, 2),
        }

        # Bullish crossover: MACD crosses above signal
        if macd_prev <= signal_prev and macd_now > signal_now:
            strength = abs(hist_now) / price * 1000  # normalized
            confidence = min(0.9, 0.5 + strength)
            return TradeRecommendation(
                pair=pair,
                signal=Signal.BUY,
                confidence=round(confidence, 2),
                reason=f"MACD bullish crossover: MACD={macd_now:.4f} crossed above signal={signal_now:.4f}",
                metadata=metadata,
            )

        # Bearish crossover: MACD crosses below signal
        if macd_prev >= signal_prev and macd_now < signal_now:
            strength = abs(hist_now) / price * 1000
            confidence = min(0.9, 0.5 + strength)
            return TradeRecommendation(
                pair=pair,
                signal=Signal.SELL,
                confidence=round(confidence, 2),
                reason=f"MACD bearish crossover: MACD={macd_now:.4f} crossed below signal={signal_now:.4f}",
                metadata=metadata,
            )

        trend = "bullish" if macd_now > signal_now else "bearish"
        return TradeRecommendation(
            pair=pair,
            signal=Signal.HOLD,
            confidence=0.3,
            reason=f"No MACD crossover. Trend: {trend}, histogram: {hist_now:.4f}",
            metadata=metadata,
        )
