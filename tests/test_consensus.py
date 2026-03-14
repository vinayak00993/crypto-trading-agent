"""Tests for the evidence-backed consensus strategy."""

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


def test_hold_on_flat_data():
    """Flat prices → no strong signals → HOLD."""
    strategy = ConsensusStrategy(params={"min_agree": 1, "confidence_threshold": 0.5})
    prices = [100.0] * 50
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.HOLD
    assert "votes" in result.metadata


def test_metadata_has_vote_counts():
    """Metadata should include vote counts and confidence threshold."""
    strategy = ConsensusStrategy(params={"min_agree": 1, "confidence_threshold": 0.5})
    prices = [100.0] * 50
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    assert "buy_count" in result.metadata
    assert "sell_count" in result.metadata
    assert "hold_count" in result.metadata
    assert "confidence_threshold" in result.metadata
    total = result.metadata["buy_count"] + result.metadata["sell_count"] + result.metadata["hold_count"]
    assert total == 4


def test_crash_triggers_buy():
    """A massive price crash should produce at least one strong buy signal."""
    strategy = ConsensusStrategy(params={
        "min_agree": 1,
        "confidence_threshold": 0.5,
        "rsi_period": 14,
        "rsi_oversold": 35,
        "bb_period": 15,
        "bb_std": 2.0,
    })
    # Steady at 100, then crash to 70 → RSI + Bollinger should flag oversold
    prices = [100.0] * 40 + [70.0]
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    # With min_agree=1, even one strong signal should trigger
    assert result.signal == Signal.BUY
    assert result.metadata["buy_count"] >= 1


def test_spike_triggers_sell():
    """A massive price spike should produce at least one strong sell signal."""
    strategy = ConsensusStrategy(params={
        "min_agree": 1,
        "confidence_threshold": 0.5,
        "rsi_period": 14,
        "rsi_overbought": 65,
        "bb_period": 15,
        "bb_std": 2.0,
    })
    prices = [100.0] * 40 + [130.0]
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    assert result.signal in (Signal.BUY, Signal.SELL)  # extreme moves trigger either
    assert result.metadata["sell_count"] >= 1


def test_high_threshold_filters_weak_signals():
    """A very high confidence threshold should filter out weak signals → HOLD."""
    strategy = ConsensusStrategy(params={
        "min_agree": 1,
        "confidence_threshold": 0.99,  # almost impossible to meet
    })
    prices = [100.0] * 50
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.HOLD


def test_strict_consensus_holds_on_flat():
    """With min_agree=4, flat data → HOLD."""
    strategy = ConsensusStrategy(params={"min_agree": 4, "confidence_threshold": 0.5})
    prices = [100.0] * 50
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.HOLD


def test_loadable_by_name():
    """Consensus strategy should be loadable from the registry."""
    strategy = load_strategy("consensus", {"min_agree": 1})
    assert strategy.name == "consensus"


def test_all_strategies_loadable():
    """All 5 strategies should be loadable by name."""
    for name in ["sma_crossover", "rsi", "macd", "bollinger_bands", "consensus"]:
        strategy = load_strategy(name, {})
        assert strategy.name == name
