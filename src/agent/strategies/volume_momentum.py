"""
Volume Momentum Strategy

Looks for volume spikes that confirm price direction.
High volume + rising price = strong buy signal.
High volume + falling price = strong sell signal.

This is a "smart volume" strategy — it doesn't just look at price,
it asks "is the market actually putting money behind this move?"

No external API needed — uses existing OHLCV candle data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation


class VolumeMomentumStrategy(BaseStrategy):
    name = "volume_momentum"
    required_history = 30

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        self.volume_period = params.get("volume_period", 20)
        self.volume_spike = params.get("volume_spike", 2.0)      # 2x average = spike
        self.price_change_periods = params.get("price_change_periods", 5)  # look at last 5 candles

    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        if len(candles) < self.required_history:
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=0.0,
                reason=f"Need {self.required_history} candles, have {len(candles)}",
            )

        close = candles["close"]
        volume = candles["volume"]

        # Calculate volume metrics
        avg_volume = volume.rolling(window=self.volume_period).mean()
        current_volume = volume.iloc[-1]
        avg_vol_value = avg_volume.iloc[-1]

        if avg_vol_value == 0 or pd.isna(avg_vol_value):
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=0.3,
                reason="Insufficient volume data",
            )

        volume_ratio = current_volume / avg_vol_value

        # Calculate price change over recent candles
        price_now = close.iloc[-1]
        price_before = close.iloc[-self.price_change_periods]
        price_change_pct = ((price_now - price_before) / price_before) * 100

        # Also check if volume has been increasing over last 3 candles
        recent_vols = volume.iloc[-3:].tolist()
        vol_increasing = all(recent_vols[i] >= recent_vols[i - 1] * 0.9 for i in range(1, len(recent_vols)))

        metadata = {
            "volume_ratio": round(volume_ratio, 2),
            "price_change_pct": round(price_change_pct, 2),
            "current_volume": round(current_volume, 2),
            "avg_volume": round(avg_vol_value, 2),
            "vol_increasing": vol_increasing,
            "price": round(price_now, 2),
        }

        # Volume spike + price rising = strong buy
        if volume_ratio >= self.volume_spike and price_change_pct > 0.5:
            confidence = min(1.0, 0.5 + (volume_ratio - self.volume_spike) * 0.1 + price_change_pct * 0.05)
            return TradeRecommendation(
                pair=pair, signal=Signal.BUY, confidence=confidence,
                reason=f"Volume spike {volume_ratio:.1f}x avg + price up {price_change_pct:+.1f}%",
                metadata=metadata,
            )

        # Volume spike + price falling = strong sell
        elif volume_ratio >= self.volume_spike and price_change_pct < -0.5:
            confidence = min(1.0, 0.5 + (volume_ratio - self.volume_spike) * 0.1 + abs(price_change_pct) * 0.05)
            return TradeRecommendation(
                pair=pair, signal=Signal.SELL, confidence=confidence,
                reason=f"Volume spike {volume_ratio:.1f}x avg + price down {price_change_pct:+.1f}%",
                metadata=metadata,
            )

        # Moderate volume increase with strong price move
        elif volume_ratio >= 1.5 and vol_increasing and price_change_pct > 1.0:
            return TradeRecommendation(
                pair=pair, signal=Signal.BUY, confidence=0.55,
                reason=f"Rising volume {volume_ratio:.1f}x avg + price up {price_change_pct:+.1f}%",
                metadata=metadata,
            )

        elif volume_ratio >= 1.5 and vol_increasing and price_change_pct < -1.0:
            return TradeRecommendation(
                pair=pair, signal=Signal.SELL, confidence=0.55,
                reason=f"Rising volume {volume_ratio:.1f}x avg + price down {price_change_pct:+.1f}%",
                metadata=metadata,
            )

        else:
            return TradeRecommendation(
                pair=pair, signal=Signal.HOLD, confidence=0.3,
                reason=f"Vol {volume_ratio:.1f}x avg, price {price_change_pct:+.1f}% — no conviction",
                metadata=metadata,
            )
