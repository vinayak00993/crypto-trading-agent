"""Tests for the paper trading executor."""

from execution.paper import PaperExecutor, OrderStatus, OrderSide


def test_buy_creates_position():
    """Buying should create a position and reduce cash."""
    ex = PaperExecutor(starting_balance=10_000)
    order = ex.buy("BTC/USDT", amount_usd=500, price=50_000, reason="test")

    assert order.status == OrderStatus.FILLED
    assert order.side == OrderSide.BUY
    assert "BTC/USDT" in ex.positions
    assert ex.cash == 9_500
    assert ex.positions["BTC/USDT"].quantity == 500 / 50_000  # 0.01 BTC


def test_buy_rejected_insufficient_funds():
    """Buying more than available cash should be rejected."""
    ex = PaperExecutor(starting_balance=100)
    order = ex.buy("BTC/USDT", amount_usd=500, price=50_000, reason="test")

    assert order.status == OrderStatus.REJECTED
    assert "BTC/USDT" not in ex.positions
    assert ex.cash == 100  # unchanged


def test_sell_closes_position():
    """Selling should remove the position and return cash."""
    ex = PaperExecutor(starting_balance=10_000)
    ex.buy("BTC/USDT", amount_usd=500, price=50_000, reason="test buy")

    order = ex.sell("BTC/USDT", price=55_000, reason="test sell")

    assert order.status == OrderStatus.FILLED
    assert "BTC/USDT" not in ex.positions
    # Bought 0.01 BTC at 50k, sold at 55k → proceeds = 550
    assert ex.cash == 9_500 + 550  # 10_050


def test_sell_rejected_no_position():
    """Selling a pair we don't hold should be rejected."""
    ex = PaperExecutor(starting_balance=10_000)
    order = ex.sell("BTC/USDT", price=50_000, reason="test")

    assert order.status == OrderStatus.REJECTED


def test_total_value_with_positions():
    """Total value should include cash + position value at current prices."""
    ex = PaperExecutor(starting_balance=10_000)
    ex.buy("BTC/USDT", amount_usd=1_000, price=50_000, reason="test")
    # Have 9000 cash + 0.02 BTC

    # If BTC goes to 60k: position worth 0.02 * 60000 = 1200
    total = ex.total_value({"BTC/USDT": 60_000})
    assert total == 9_000 + 1_200  # 10_200


def test_summary_shows_pnl():
    """Summary should calculate correct P&L."""
    ex = PaperExecutor(starting_balance=10_000)
    ex.buy("BTC/USDT", amount_usd=1_000, price=50_000, reason="test")

    summary = ex.summary({"BTC/USDT": 55_000})
    assert summary["total_pnl"] > 0
    assert summary["open_positions"] == 1
    assert summary["total_trades"] == 1
