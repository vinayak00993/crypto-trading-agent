"""Tests for the portfolio manager and risk controls."""

from agent.config import RiskConfig
from execution.paper import PaperExecutor
from portfolio.manager import PortfolioManager


def _make_portfolio(
    balance: float = 10_000,
    max_position_pct: float = 5.0,
    max_open_positions: int = 3,
    stop_loss_pct: float = 3.0,
    take_profit_pct: float = 6.0,
) -> PortfolioManager:
    """Helper: build a PortfolioManager with custom settings."""
    risk = RiskConfig(
        max_position_pct=max_position_pct,
        max_open_positions=max_open_positions,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        max_daily_loss_pct=10.0,
    )
    executor = PaperExecutor(starting_balance=balance)
    return PortfolioManager(risk, executor)


def test_buy_respects_position_size_limit():
    """Each trade should use at most max_position_pct of portfolio."""
    pm = _make_portfolio(balance=10_000, max_position_pct=5.0)
    prices = {"BTC/USDT": 50_000}

    pm.try_buy("BTC/USDT", price=50_000, current_prices=prices, reason="test")

    # Should have spent ~5% of 10k = $500
    assert pm.executor.cash >= 9_400  # roughly 10000 - 500 (allowing some rounding)
    assert pm.executor.cash <= 9_600


def test_max_positions_enforced():
    """Should reject buys when max open positions is reached."""
    pm = _make_portfolio(balance=10_000, max_open_positions=2)
    prices = {"BTC/USDT": 50_000, "ETH/USDT": 3_000, "SOL/USDT": 150}

    pm.try_buy("BTC/USDT", price=50_000, current_prices=prices, reason="test")
    pm.try_buy("ETH/USDT", price=3_000, current_prices=prices, reason="test")

    # Third buy should be blocked
    result = pm.try_buy("SOL/USDT", price=150, current_prices=prices, reason="test")
    assert result is False
    assert "SOL/USDT" not in pm.executor.positions


def test_stop_loss_triggers():
    """Position should auto-close when loss exceeds stop_loss_pct."""
    pm = _make_portfolio(balance=10_000, stop_loss_pct=3.0)
    prices = {"BTC/USDT": 50_000}

    pm.try_buy("BTC/USDT", price=50_000, current_prices=prices, reason="test")
    assert "BTC/USDT" in pm.executor.positions

    # Price drops 5% → should trigger 3% stop-loss
    new_prices = {"BTC/USDT": 47_000}
    closed = pm.check_stop_loss_take_profit(new_prices)

    assert "BTC/USDT" in closed
    assert "BTC/USDT" not in pm.executor.positions


def test_take_profit_triggers():
    """Position should auto-close when gain exceeds take_profit_pct."""
    pm = _make_portfolio(balance=10_000, take_profit_pct=6.0)
    prices = {"BTC/USDT": 50_000}

    pm.try_buy("BTC/USDT", price=50_000, current_prices=prices, reason="test")

    # Price rises 8% → should trigger 6% take-profit
    new_prices = {"BTC/USDT": 54_000}
    closed = pm.check_stop_loss_take_profit(new_prices)

    assert "BTC/USDT" in closed
    assert "BTC/USDT" not in pm.executor.positions


def test_no_duplicate_positions():
    """Trying to buy a pair we already hold should be rejected."""
    pm = _make_portfolio(balance=10_000)
    prices = {"BTC/USDT": 50_000}

    pm.try_buy("BTC/USDT", price=50_000, current_prices=prices, reason="first buy")
    result = pm.try_buy("BTC/USDT", price=50_000, current_prices=prices, reason="second buy")

    assert result is False
