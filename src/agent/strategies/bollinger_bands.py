"""
Bollinger Bands Strategy.

Bollinger Bands create a channel around the price using standard deviations.
When price touches the lower band → potential buy (oversold).
When price touches the upper band → potential sell (overbought).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation


class BollingerBandsStrategy(BaseStrategy):
    """
    Bollinger Bands mean-reversion strategy.

    Config params:
        period (int): Moving average period. Default 20.
        std_dev (float): Number of standard deviations. Default 2.0.
    """

    @property
    def name(self) -> str:
        return "bollinger_bands"

    @property
    def required_history(self) -> int:
        return self.params.get("period", 20) + 5

    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        period = self.params.get("period", 20)
        std_dev = self.params.get("std_dev", 2.0)

        if len(candles) < period + 2:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.HOLD,
                confidence=0.0,
                reason=f"Not enough data: have {len(candles)}, need {period + 2}",
                metadata={},
            )

        close = candles["close"]
        sma = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()

        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)

        price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2])
        upper = float(upper_band.iloc[-1])
        lower = float(lower_band.iloc[-1])
        middle = float(sma.iloc[-1])

        # %B indicator: where price sits within the bands (0 = lower, 1 = upper)
        band_width = upper - lower
        pct_b = (price - lower) / band_width if band_width > 0 else 0.5

        metadata: dict[str, Any] = {
            "price": round(price, 2),
            "upper_band": round(upper, 2),
            "lower_band": round(lower, 2),
            "middle_band": round(middle, 2),
            "pct_b": round(pct_b, 4),
            "band_width": round(band_width, 2),
        }

        # Price crosses below lower band → BUY (oversold bounce)
        if price <= lower and prev_price > lower:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.BUY,
                confidence=0.75,
                reason=f"Price broke below lower Bollinger Band: ${price:.2f} < ${lower:.2f}",
                metadata=metadata,
            )

        # Price well below lower band → strong BUY
        if price < lower:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.BUY,
                confidence=0.6,
                reason=f"Price below lower band: ${price:.2f}, %B={pct_b:.2f}",
                metadata=metadata,
            )

        # Price crosses above upper band → SELL (overbought)
        if price >= upper and prev_price < upper:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.SELL,
                confidence=0.75,
                reason=f"Price broke above upper Bollinger Band: ${price:.2f} > ${upper:.2f}",
                metadata=metadata,
            )

        # Price well above upper band → strong SELL
        if price > upper:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.SELL,
                confidence=0.6,
                reason=f"Price above upper band: ${price:.2f}, %B={pct_b:.2f}",
                metadata=metadata,
            )

        return TradeRecommendation(
            pair=pair,
            signal=Signal.HOLD,
            confidence=0.3,
            reason=f"Price within bands: %B={pct_b:.2f} (0=lower, 1=upper)",
            metadata=metadata,
        )
