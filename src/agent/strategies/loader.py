"""
Strategy registry — maps config names to strategy classes.

To add a new strategy:
  1. Create a new file in strategies/ that subclasses BaseStrategy
  2. Register it in STRATEGY_REGISTRY below
"""

from __future__ import annotations

from typing import Any

from agent.strategies.base import BaseStrategy
from agent.strategies.sma_crossover import SMACrossoverStrategy
from agent.strategies.rsi import RSIStrategy
from agent.strategies.macd import MACDStrategy
from agent.strategies.bollinger_bands import BollingerBandsStrategy

# Add new strategies here
STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "sma_crossover": SMACrossoverStrategy,
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "bollinger_bands": BollingerBandsStrategy,
}


def load_strategy(name: str, params: dict[str, Any]) -> BaseStrategy:
    """
    Instantiate a strategy by its config name.

    Parameters
    ----------
    name : str
        The strategy name from config.yaml (e.g. "sma_crossover").
    params : dict
        Strategy-specific parameters.

    Returns
    -------
    BaseStrategy

    Raises
    ------
    ValueError
        If the strategy name isn't registered.
    """
    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        available = ", ".join(STRATEGY_REGISTRY.keys())
        raise ValueError(f"Unknown strategy: '{name}'. Available: {available}")
    return cls(params)
