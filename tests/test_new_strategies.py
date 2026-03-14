"""Tests for RSI, MACD, and Bollinger Bands strategies."""

import pandas as pd

from agent.strategies.base import Signal
from agent.strategies.rsi import RSIStrategy
from agent.strategies.macd import MACDStrategy
from agent.strategies.bollinger_bands import BollingerBandsStrategy
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
        index=pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC"),
    )


# --- RSI Tests ---

def test_rsi_oversold_buy():
    """RSI dropping below 30 should trigger BUY."""
    strategy = RSIStrategy(params={"period": 14, "oversold": 30, "overbought": 70})
    # Steady decline to push RSI into oversold territory
    prices = [100 - i * 0.8 for i in range(30)]  # 100 → ~76, consistent drops
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    # With consistent drops, RSI should be very low → BUY
    assert result.signal == Signal.BUY
    assert result.metadata["rsi"] < 35


def test_rsi_overbought_sell():
    """RSI rising above 70 should trigger SELL."""
    strategy = RSIStrategy(params={"period": 14, "oversold": 30, "overbought": 70})
    # Steady rise to push RSI into overbought
    prices = [100 + i * 0.8 for i in range(30)]  # consistent gains
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.SELL
    assert result.metadata["rsi"] > 65


def test_rsi_neutral_hold():
    """Flat prices should keep RSI neutral → HOLD."""
    strategy = RSIStrategy(params={"period": 14})
    prices = [100.0 + (i % 2) * 0.1 for i in range(30)]  # tiny oscillation
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.HOLD


# --- MACD Tests ---

def test_macd_hold_on_flat():
    """Flat data → no crossover → HOLD."""
    strategy = MACDStrategy(params={"fast_period": 12, "slow_period": 26, "signal_period": 9})
    prices = [100.0] * 50
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.HOLD


def test_macd_insufficient_data():
    """Not enough candles → HOLD."""
    strategy = MACDStrategy(params={"fast_period": 12, "slow_period": 26, "signal_period": 9})
    prices = [100.0] * 10
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.HOLD
    assert "not enough" in result.reason.lower()


# --- Bollinger Bands Tests ---

def test_bollinger_below_lower_band_buy():
    """Price below lower band → BUY."""
    strategy = BollingerBandsStrategy(params={"period": 20, "std_dev": 2.0})
    # Stable, then sharp drop on last candle
    prices = [100.0] * 25 + [80.0]  # big drop pushes below lower band
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.BUY


def test_bollinger_above_upper_band_sell():
    """Price above upper band → SELL."""
    strategy = BollingerBandsStrategy(params={"period": 20, "std_dev": 2.0})
    # Stable, then sharp spike
    prices = [100.0] * 25 + [120.0]  # big spike pushes above upper band
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.SELL


def test_bollinger_within_bands_hold():
    """Price within bands → HOLD."""
    strategy = BollingerBandsStrategy(params={"period": 20, "std_dev": 2.0})
    prices = [100.0] * 30
    candles = _make_candles(prices)
    result = strategy.evaluate("BTC/USDT", candles)
    assert result.signal == Signal.HOLD


# --- Strategy Loader Tests ---

def test_loader_finds_all_strategies():
    """All four strategies should be loadable by name."""
    for name in ["sma_crossover", "rsi", "macd", "bollinger_bands"]:
        strategy = load_strategy(name, {})
        assert strategy.name == name
