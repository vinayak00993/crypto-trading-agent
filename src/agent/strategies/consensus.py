"""
Consensus Strategy — runs ALL strategies and trades when multiple agree.

Instead of relying on a single strategy, the consensus approach runs
SMA Crossover, RSI, MACD, and Bollinger Bands on every tick. It only
executes a trade when a configurable number of strategies agree on the
same signal.

This reduces false signals and increases confidence in each trade.
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
    Meta-strategy that runs all sub-strategies and trades on agreement.

    Config params:
        min_agree (int): Minimum strategies that must agree. Default 2.
        fast_period (int): SMA fast period. Default 5 (tuned for 5m candles).
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
        self.min_agree = params.get("min_agree", 2)

        # Build sub-strategies with tuned params for short timeframes
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

        # Count votes
        buy_votes: list[str] = []
        sell_votes: list[str] = []
        hold_votes: list[str] = []
        all_reasons: list[str] = []
        total_confidence = 0.0

        strategy_details: dict[str, Any] = {}

        for rec in results:
            strategy_name = rec.metadata.get("strategy_name", rec.reason[:20])
            # Try to identify which strategy produced this
            for s in self._strategies:
                if s.evaluate.__qualname__.split(".")[0] in type(s).__name__:
                    strategy_name = s.name
                    break

            if rec.signal == Signal.BUY:
                buy_votes.append(rec.reason)
                total_confidence += rec.confidence
            elif rec.signal == Signal.SELL:
                sell_votes.append(rec.reason)
                total_confidence += rec.confidence
            else:
                hold_votes.append(rec.reason)

            all_reasons.append(f"{rec.signal.value}({rec.confidence:.0%})")

        # Build detailed metadata for the dashboard
        vote_summary = []
        for i, rec in enumerate(results):
            s_name = self._strategies[i].name if i < len(self._strategies) else f"strategy_{i}"
            vote_summary.append(f"{s_name}={rec.signal.value}")
            strategy_details[s_name] = {
                "signal": rec.signal.value,
                "confidence": rec.confidence,
                "reason": rec.reason,
            }

        metadata: dict[str, Any] = {
            "buy_count": len(buy_votes),
            "sell_count": len(sell_votes),
            "hold_count": len(hold_votes),
            "min_agree": self.min_agree,
            "votes": ", ".join(vote_summary),
            "strategies": strategy_details,
            "price": float(candles["close"].iloc[-1]),
        }

        # Decide: BUY if enough strategies agree
        if len(buy_votes) >= self.min_agree:
            avg_confidence = total_confidence / len(results)
            agreement_bonus = len(buy_votes) / len(results)  # higher when more agree
            final_confidence = min(0.95, avg_confidence * 0.5 + agreement_bonus * 0.5)

            return TradeRecommendation(
                pair=pair,
                signal=Signal.BUY,
                confidence=round(final_confidence, 2),
                reason=f"CONSENSUS BUY: {len(buy_votes)}/{len(results)} agree [{', '.join(vote_summary)}]",
                metadata=metadata,
            )

        # SELL if enough strategies agree
        if len(sell_votes) >= self.min_agree:
            avg_confidence = total_confidence / len(results)
            agreement_bonus = len(sell_votes) / len(results)
            final_confidence = min(0.95, avg_confidence * 0.5 + agreement_bonus * 0.5)

            return TradeRecommendation(
                pair=pair,
                signal=Signal.SELL,
                confidence=round(final_confidence, 2),
                reason=f"CONSENSUS SELL: {len(sell_votes)}/{len(results)} agree [{', '.join(vote_summary)}]",
                metadata=metadata,
            )

        # No consensus — hold
        return TradeRecommendation(
            pair=pair,
            signal=Signal.HOLD,
            confidence=0.3,
            reason=f"No consensus: {len(buy_votes)}B/{len(sell_votes)}S/{len(hold_votes)}H [{', '.join(vote_summary)}]",
            metadata=metadata,
        )
