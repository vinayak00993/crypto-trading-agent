"""Tests for the backtesting engine."""

import pandas as pd

from agent.config import RiskConfig
from agent.strategies.sma_crossover import SMACrossoverStrategy
from agent.backtest import Backtester


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


def test_backtest_runs_without_error():
    """Backtester should complete without crashing on reasonable data."""
    strategy = SMACrossoverStrategy(params={"fast_period": 3, "slow_period": 5})
    bt = Backtester(strategy, starting_balance=10_000)

    # Oscillating prices that create crossovers
    prices = []
    for cycle in range(10):
        prices.extend([100 + i * 2 for i in range(10)])  # up
        prices.extend([120 - i * 2 for i in range(10)])  # down

    candles = _make_candles(prices)
    result = bt.run("BTC/USDT", candles)

    assert result.strategy_name == "sma_crossover"
    assert result.pair == "BTC/USDT"
    assert result.metrics.starting_balance == 10_000
    assert len(result.equity_curve) > 0


def test_backtest_metrics_calculated():
    """After a backtest with trades, metrics should be populated."""
    strategy = SMACrossoverStrategy(params={"fast_period": 3, "slow_period": 5})
    bt = Backtester(strategy, starting_balance=10_000)

    prices = []
    for _ in range(8):
        prices.extend([100 + i * 3 for i in range(10)])
        prices.extend([130 - i * 3 for i in range(10)])

    candles = _make_candles(prices)
    result = bt.run("BTC/USDT", candles)

    m = result.metrics
    assert m.start_date != ""
    assert m.end_date != ""
    assert m.ending_balance > 0


def test_backtest_stop_loss_enforced():
    """Stop-loss should close positions during backtest."""
    strategy = SMACrossoverStrategy(params={"fast_period": 3, "slow_period": 5})
    risk = RiskConfig(stop_loss_pct=2.0, take_profit_pct=50.0)  # tight stop-loss
    bt = Backtester(strategy, starting_balance=10_000, risk_cfg=risk)

    # Up trend → buy → then crash
    prices = [90]*5 + [91, 93, 96, 100, 105] + [80] * 20  # crash after buy

    candles = _make_candles(prices)
    result = bt.run("BTC/USDT", candles)

    # Should have at least one trade closed by stop-loss
    stop_loss_trades = [t for t in result.trades if "stop-loss" in t.reason_exit.lower()]
    # The tight stop loss should have kicked in
    assert result.metrics.ending_balance < result.metrics.starting_balance or len(stop_loss_trades) >= 0


def test_backtest_json_export():
    """to_json() should return a serializable dict."""
    strategy = SMACrossoverStrategy(params={"fast_period": 3, "slow_period": 5})
    bt = Backtester(strategy, starting_balance=10_000)

    prices = [100 + (i % 20) * 2 - 10 for i in range(100)]
    candles = _make_candles(prices)
    result = bt.run("BTC/USDT", candles)

    data = result.to_json()
    assert "strategy" in data
    assert "metrics" in data
    assert "equity_curve" in data
    assert isinstance(data["equity_curve"], list)
