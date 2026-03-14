"""
RSI (Relative Strength Index) Strategy.

Buys when RSI drops below the oversold threshold (asset is cheap),
sells when RSI rises above the overbought threshold (asset is expensive).

RSI ranges from 0 to 100:
  - Below 30 = oversold (potential buy)
  - Above 70 = overbought (potential sell)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation


class RSIStrategy(BaseStrategy):
    """
    RSI-based mean-reversion strategy.

    Config params:
        period (int): RSI lookback period. Default 14.
        oversold (float): Buy threshold. Default 30.
        overbought (float): Sell threshold. Default 70.
    """

    @property
    def name(self) -> str:
        return "rsi"

    @property
    def required_history(self) -> int:
        return self.params.get("period", 14) + 10

    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        period = self.params.get("period", 14)
        oversold = self.params.get("oversold", 30)
        overbought = self.params.get("overbought", 70)

        if len(candles) < period + 2:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.HOLD,
                confidence=0.0,
                reason=f"Not enough data: have {len(candles)}, need {period + 2}",
                metadata={},
            )

        # Calculate RSI
        delta = candles["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()

        rs = gain / loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))

        current_rsi = float(rsi.iloc[-1])
        prev_rsi = float(rsi.iloc[-2])
        price = float(candles["close"].iloc[-1])

        metadata: dict[str, Any] = {
            "rsi": round(current_rsi, 2),
            "prev_rsi": round(prev_rsi, 2),
            "price": round(price, 2),
            "period": period,
            "oversold": oversold,
            "overbought": overbought,
        }

        # RSI crossing below oversold → BUY
        if current_rsi < oversold and prev_rsi >= oversold:
            confidence = min(1.0, (oversold - current_rsi) / oversold)
            return TradeRecommendation(
                pair=pair,
                signal=Signal.BUY,
                confidence=round(confidence, 2),
                reason=f"RSI crossed below oversold: RSI={current_rsi:.1f} < {oversold}",
                metadata=metadata,
            )

        # Already oversold → BUY (weaker signal)
        if current_rsi < oversold:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.BUY,
                confidence=0.5,
                reason=f"RSI in oversold zone: RSI={current_rsi:.1f}",
                metadata=metadata,
            )

        # RSI crossing above overbought → SELL
        if current_rsi > overbought and prev_rsi <= overbought:
            confidence = min(1.0, (current_rsi - overbought) / (100 - overbought))
            return TradeRecommendation(
                pair=pair,
                signal=Signal.SELL,
                confidence=round(confidence, 2),
                reason=f"RSI crossed above overbought: RSI={current_rsi:.1f} > {overbought}",
                metadata=metadata,
            )

        # Already overbought → SELL (weaker signal)
        if current_rsi > overbought:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.SELL,
                confidence=0.5,
                reason=f"RSI in overbought zone: RSI={current_rsi:.1f}",
                metadata=metadata,
            )

        return TradeRecommendation(
            pair=pair,
            signal=Signal.HOLD,
            confidence=0.3,
            reason=f"RSI neutral: {current_rsi:.1f} (range: {oversold}-{overbought})",
            metadata=metadata,
        )
