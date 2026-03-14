"""
Abstract base class for all trading strategies.

Every strategy you write should subclass `BaseStrategy` and implement
the `evaluate` method. The agent loop calls `evaluate()` on each tick
and acts on the returned Signal.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd


class Signal(Enum):
    """What the strategy wants the agent to do."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeRecommendation:
    """A strategy's output for one trading pair."""
    pair: str
    signal: Signal
    confidence: float          # 0.0 – 1.0
    reason: str                # Human-readable explanation
    metadata: dict[str, Any]   # Extra info (indicator values, etc.)


class BaseStrategy(ABC):
    """
    Interface that every strategy must implement.

    Parameters
    ----------
    params : dict
        Strategy-specific parameters loaded from config.yaml
        (e.g. {"fast_period": 10, "slow_period": 30}).
    """

    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this strategy."""
        ...

    @property
    def required_history(self) -> int:
        """Minimum number of candles needed before the strategy can evaluate."""
        return 50  # sensible default; override in subclasses

    @abstractmethod
    def evaluate(self, pair: str, candles: pd.DataFrame) -> TradeRecommendation:
        """
        Analyse recent candle data and return a trade recommendation.

        Parameters
        ----------
        pair : str
            The trading pair, e.g. "BTC/USDT".
        candles : pd.DataFrame
            OHLCV data with columns: open, high, low, close, volume.
            Index is a DatetimeIndex. Most recent candle is the last row.

        Returns
        -------
        TradeRecommendation
        """
        ...
