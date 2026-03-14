"""
Consensus Strategy — runs ALL strategies, trades when any has a strong signal.

Evidence-backed approach (Bates & Granger 1969, forecast combination literature):
- Runs 4 diverse strategies (trend, momentum, volatility) every tick
- Equal weights — research shows this beats complex optimization
- Trades when ANY strategy signals with confidence above a threshold
- More strategies agreeing = higher confidence = larger position sizing potential
- Filters out weak/noisy signals via confidence_threshold

This produces frequent trades while avoiding low-quality signals.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from agent.strategies.base import BaseStrategy, Signal, TradeRecommendation
from agent.strategies.sma_crossover import SMACrossoverStrategy
from agent.strategies.rsi import RSIStrategy
from agent.strategies.macd import MACDStrategy
from agent.strategies.bollinger_bands import BollingerBandsStrategy

log = structlog.get_logger()


class ConsensusStrategy(BaseStrategy):
    """
    Meta-strategy: runs all sub-strategies, trades on strong individual signals.

    Config params:
        min_agree (int): Minimum strategies that must agree. Default 1.
        confidence_threshold (float): Minimum confidence to act. Default 0.5.
        fast_period (int): SMA fast period. Default 5.
        slow_period (int): SMA slow period. Default 15.
        rsi_period (int): RSI lookback. Default 14.
        rsi_oversold (float): RSI buy threshold. Default 35.
        rsi_overbought (float): RSI sell threshold. Default 65.
        macd_fast (int): MACD fast EMA. Default 8.
        macd_slow (int): MACD slow EMA. Default 21.
        macd_signal (int): MACD signal period. Default 5.
        bb_period (int): Bollinger Bands period. Default 15.
        bb_std (float): Bollinger Bands std dev. Default 2.0.
    """

    def __init__(self, params: dict[str, Any]) -> None:
        super().__init__(params)
        self.min_agree = params.get("min_agree", 1)
        self.confidence_threshold = params.get("confidence_threshold", 0.5)

        # Build sub-strategies — diverse by design (trend + momentum + volatility)
        self._strategies: list[BaseStrategy] = [
            SMACrossoverStrategy({
                "fast_period": params.get("fast_period", 5),
                "slow_period": params.get("slow_period", 15),
            }),
            RSIStrategy({
                "period": params.get("rsi_period", 14),
                "oversold": params.get("rsi_oversold", 35),
                "overbought": params.get("rsi_overbought", 65),
            }),
            MACDStrategy({
                "fast_period": params.get("macd_fast", 8),
                "slow_period": params.get("macd_slow", 21),
                "signal_period": params.get("macd_signal", 5),
            }),
            BollingerBandsStrategy({
                "period": params.get("bb_period", 15),
                "std_dev": params.get("bb_std", 2.0),
            }),
        ]

    @property
    def name(self) -> str:
        return "consensus"

    @property
    def required_history(self) -> int:
        return max(s.required_history for s in self._strategies) + 5

    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        # Run every sub-strategy
        results: list[TradeRecommendation] = []
        for strategy in self._strategies:
            try:
                rec = strategy.evaluate(pair, candles)
                results.append(rec)
            except Exception as e:
                log.warning("consensus.sub_strategy_error", strategy=strategy.name, error=str(e))

        if not results:
            return TradeRecommendation(
                pair=pair,
                signal=Signal.HOLD,
                confidence=0.0,
                reason="No sub-strategies returned results",
                metadata={},
            )

        # Collect votes — only count signals above the confidence threshold
        strong_buys: list[tuple[str, float]] = []   # (strategy_name, confidence)
        strong_sells: list[tuple[str, float]] = []
        all_votes: list[str] = []

        strategy_details: dict[str, Any] = {}

        for i, rec in enumerate(results):
            s_name = self._strategies[i].name if i < len(self._strategies) else f"strategy_{i}"
            all_votes.append(f"{s_name}={rec.signal.value}")

            strategy_details[s_name] = {
                "signal": rec.signal.value,
                "confidence": rec.confidence,
                "reason": rec.reason,
            }

            # Only count strong signals (above confidence threshold)
            if rec.signal == Signal.BUY and rec.confidence >= self.confidence_threshold:
                strong_buys.append((s_name, rec.confidence))
            elif rec.signal == Signal.SELL and rec.confidence >= self.confidence_threshold:
                strong_sells.append((s_name, rec.confidence))

        metadata: dict[str, Any] = {
            "buy_count": len(strong_buys),
            "sell_count": len(strong_sells),
            "hold_count": len(results) - len(strong_buys) - len(strong_sells),
            "min_agree": self.min_agree,
            "confidence_threshold": self.confidence_threshold,
            "votes": ", ".join(all_votes),
            "strategies": strategy_details,
            "price": float(candles["close"].iloc[-1]),
        }

        # BUY: enough strong buy signals
        if len(strong_buys) >= self.min_agree:
            # Equal-weight average of confident strategies (research-backed)
            avg_confidence = sum(c for _, c in strong_buys) / len(strong_buys)
            # Bonus for agreement: more strategies = stronger signal
            agreement_ratio = len(strong_buys) / len(results)
            final_confidence = min(0.95, avg_confidence * 0.7 + agreement_ratio * 0.3)

            names = [n for n, _ in strong_buys]
            return TradeRecommendation(
                pair=pair,
                signal=Signal.BUY,
                confidence=round(final_confidence, 2),
                reason=f"BUY ({len(strong_buys)}/{len(results)} strong): {', '.join(names)} [{', '.join(all_votes)}]",
                metadata=metadata,
            )

        # SELL: enough strong sell signals
        if len(strong_sells) >= self.min_agree:
            avg_confidence = sum(c for _, c in strong_sells) / len(strong_sells)
            agreement_ratio = len(strong_sells) / len(results)
            final_confidence = min(0.95, avg_confidence * 0.7 + agreement_ratio * 0.3)

            names = [n for n, _ in strong_sells]
            return TradeRecommendation(
                pair=pair,
                signal=Signal.SELL,
                confidence=round(final_confidence, 2),
                reason=f"SELL ({len(strong_sells)}/{len(results)} strong): {', '.join(names)} [{', '.join(all_votes)}]",
                metadata=metadata,
            )

        # No strong signals — hold
        return TradeRecommendation(
            pair=pair,
            signal=Signal.HOLD,
            confidence=0.2,
            reason=f"No strong signals (threshold={self.confidence_threshold}): [{', '.join(all_votes)}]",
            metadata=metadata,
        )
