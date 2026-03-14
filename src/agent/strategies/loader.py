"""
Strategy registry — maps config names to strategy classes.

Strategies are grouped into:
  - TECHNICAL: Price/chart-based (SMA, RSI, MACD, Bollinger)
  - FUNDAMENTAL: On-chain, sentiment, volume (Fear&Greed, Network, Volume, DCA)
  - META: Combines other strategies (Consensus)
"""

from __future__ import annotations

from typing import Any

from agent.strategies.base import BaseStrategy
from agent.strategies.sma_crossover import SMACrossoverStrategy
from agent.strategies.rsi import RSIStrategy
from agent.strategies.macd import MACDStrategy
from agent.strategies.bollinger_bands import BollingerBandsStrategy
from agent.strategies.consensus import ConsensusStrategy
from agent.strategies.fear_greed import FearGreedStrategy
from agent.strategies.network_activity import NetworkActivityStrategy
from agent.strategies.volume_momentum import VolumeMomentumStrategy
from agent.strategies.dca_baseline import DCABaselineStrategy

# All strategies
STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "sma_crossover": SMACrossoverStrategy,
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "bollinger_bands": BollingerBandsStrategy,
    "consensus": ConsensusStrategy,
    "fear_greed": FearGreedStrategy,
    "network_activity": NetworkActivityStrategy,
    "volume_momentum": VolumeMomentumStrategy,
    "dca_baseline": DCABaselineStrategy,
}

# Group labels for the dashboard
TECHNICAL_STRATEGIES = ["sma_crossover", "rsi", "macd", "bollinger_bands"]
FUNDAMENTAL_STRATEGIES = ["fear_greed", "network_activity", "volume_momentum", "dca_baseline"]
META_STRATEGIES = ["consensus"]


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
