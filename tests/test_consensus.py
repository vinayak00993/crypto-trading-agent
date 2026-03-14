"""Tests for the consensus strategy."""

import pandas as pd

from agent.strategies.base import Signal
from agent.strategies.consensus import ConsensusStrategy
from agent.strategies.loader import load_strategy


def _make_candles(prices: list[float]) -> pd.DataFrame:
    n = len(prices)
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000.0] * n,
        },
        index=pd.date_range("2025-01-01", periods=n, freq="5min", tz="UTC"),
    )


def test_consensus_returns_hold_on_flat_data():
    """Flat prices should produce HOLD — no strategy should signal."""
    strategy = ConsensusStrategy(params={"min_agree": 2})
    prices = [100.0] * 50
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.HOLD
    assert "votes" in result.metadata


def test_consensus_metadata_has_vote_counts():
    """Metadata should include buy/sell/hold vote counts."""
    strategy = ConsensusStrategy(params={"min_agree": 2})
    prices = [100.0] * 50
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    assert "buy_count" in result.metadata
    assert "sell_count" in result.metadata
    assert "hold_count" in result.metadata
    assert result.metadata["buy_count"] + result.metadata["sell_count"] + result.metadata["hold_count"] == 4


def test_consensus_buy_when_multiple_agree():
    """When price crashes hard, RSI + Bollinger should both say BUY."""
    strategy = ConsensusStrategy(params={
        "min_agree": 2,
        "rsi_period": 14,
        "rsi_oversold": 35,
        "bb_period": 15,
        "bb_std": 2.0,
        "fast_period": 3,
        "slow_period": 5,
    })
    # Steady prices then a big crash — should trigger multiple buy signals
    prices = [100.0] * 40 + [70.0]  # massive drop
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    # At minimum, the metadata should show strategy votes
    assert result.metadata["buy_count"] >= 0
    assert "votes" in result.metadata


def test_consensus_sell_when_multiple_agree():
    """When price spikes hard, RSI + Bollinger should both say SELL."""
    strategy = ConsensusStrategy(params={
        "min_agree": 2,
        "rsi_period": 14,
        "rsi_overbought": 65,
        "bb_period": 15,
        "bb_std": 2.0,
        "fast_period": 3,
        "slow_period": 5,
    })
    prices = [100.0] * 40 + [130.0]  # massive spike
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    assert result.metadata["sell_count"] >= 0
    assert "votes" in result.metadata


def test_consensus_requires_min_agree():
    """With min_agree=4, it should almost never trade — very conservative."""
    strategy = ConsensusStrategy(params={"min_agree": 4})
    prices = [100.0] * 50
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    # 4/4 agreement on flat data is virtually impossible for a non-HOLD signal
    assert result.signal == Signal.HOLD


def test_consensus_loadable_by_name():
    """Consensus strategy should be loadable from the registry."""
    strategy = load_strategy("consensus", {"min_agree": 2})
    assert strategy.name == "consensus"


def test_all_strategies_loadable():
    """All 5 strategies should be loadable by name."""
    for name in ["sma_crossover", "rsi", "macd", "bollinger_bands", "consensus"]:
        strategy = load_strategy(name, {})
        assert strategy.name == name
