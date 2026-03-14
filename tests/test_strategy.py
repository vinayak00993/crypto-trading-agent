"""Tests for the SMA Crossover strategy."""

import pandas as pd

from agent.strategies.base import Signal
from agent.strategies.sma_crossover import SMACrossoverStrategy


def _make_candles(prices: list[float]) -> pd.DataFrame:
    """Helper: build a candle DataFrame from a list of close prices."""
    n = len(prices)
    df = pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [1000.0] * n,
        },
        index=pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC"),
    )
    return df


def test_bullish_crossover_generates_buy():
    """When fast SMA crosses above slow SMA → BUY signal."""
    strategy = SMACrossoverStrategy(params={"fast_period": 3, "slow_period": 5})

    # Flat at 100, then dip to 90 (puts fast SMA below slow SMA),
    # then spike to 110 on the last candle (fast SMA jumps above slow SMA).
    # At candle -2: SMA(3)=90.0, SMA(5)=92.0  → fast < slow
    # At candle -1: SMA(3)=96.7, SMA(5)=94.0  → fast > slow  ← crossover!
    prices = [100]*10 + [90, 90, 90, 90, 110]

    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    assert result.signal == Signal.BUY
    assert result.confidence > 0
    assert "bullish" in result.reason.lower()


def test_bearish_crossover_generates_sell():
    """When fast SMA crosses below slow SMA → SELL signal."""
    strategy = SMACrossoverStrategy(params={"fast_period": 3, "slow_period": 5})

    # Flat at 100, then pump to 110 (puts fast SMA above slow SMA),
    # then crash to 85 on the last candle (fast SMA drops below slow SMA).
    # At candle -2: SMA(3)=110.0, SMA(5)=108.0  → fast > slow
    # At candle -1: SMA(3)=101.7, SMA(5)=105.0  → fast < slow  ← crossover!
    prices = [100]*10 + [110, 110, 110, 110, 85]

    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    assert result.signal == Signal.SELL
    assert result.confidence > 0
    assert "bearish" in result.reason.lower()


def test_hold_when_no_crossover():
    """Flat prices → HOLD signal."""
    strategy = SMACrossoverStrategy(params={"fast_period": 3, "slow_period": 5})

    # Very flat prices — no crossover
    prices = [100.0] * 20

    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    assert result.signal == Signal.HOLD


def test_hold_when_insufficient_data():
    """Not enough candles → HOLD with explanation."""
    strategy = SMACrossoverStrategy(params={"fast_period": 3, "slow_period": 10})

    prices = [100.0] * 5  # only 5 candles, need 12+
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)

    assert result.signal == Signal.HOLD
    assert "not enough" in result.reason.lower()


def test_strategy_loader():
    """The strategy loader should find sma_crossover by name."""
    from agent.strategies.loader import load_strategy

    strategy = load_strategy("sma_crossover", {"fast_period": 5, "slow_period": 20})
    assert strategy.name == "sma_crossover"
    assert strategy.params["fast_period"] == 5
