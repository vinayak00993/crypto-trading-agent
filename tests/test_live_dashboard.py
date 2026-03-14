"""Tests for the multi-pod state store and dashboard server."""

from agent.state import StateStore


def test_state_store_update():
    store = StateStore()
    store.update(status="running", tick=5)
    snap = store.snapshot()
    assert snap["status"] == "running"
    assert snap["tick"] == 5


def test_state_store_pod_tracking():
    """Each pod should be tracked independently."""
    store = StateStore()
    store.update_pod("sma_crossover", {"total_value": 2550, "pnl": 50, "pnl_pct": 2.0})
    store.update_pod("rsi", {"total_value": 2480, "pnl": -20, "pnl_pct": -0.8})

    snap = store.snapshot()
    assert "sma_crossover" in snap["pods"]
    assert "rsi" in snap["pods"]
    assert snap["pods"]["sma_crossover"]["pnl"] == 50
    assert snap["pods"]["rsi"]["pnl"] == -20


def test_state_store_pod_equity():
    """Per-pod equity points should be tracked separately."""
    store = StateStore()
    store.add_pod_equity_point("sma_crossover", 2500)
    store.add_pod_equity_point("sma_crossover", 2520)
    store.add_pod_equity_point("rsi", 2500)

    snap = store.snapshot()
    assert len(snap["pod_equity"]["sma_crossover"]) == 2
    assert len(snap["pod_equity"]["rsi"]) == 1


def test_state_store_signals_with_pod():
    """Signals should include pod name."""
    store = StateStore()
    store.add_signal({"pod": "rsi", "pair": "BTC/USDT", "signal": "BUY"})

    snap = store.snapshot()
    assert snap["signals"][0]["pod"] == "rsi"


def test_state_store_trades_with_pod():
    """Trades should include pod name."""
    store = StateStore()
    store.add_trade({"pod": "macd", "pair": "ETH/USDT", "side": "BUY", "price": 2000})

    snap = store.snapshot()
    assert snap["trade_log"][0]["pod"] == "macd"


def test_combined_equity():
    store = StateStore()
    store.add_equity_point(10000)
    store.add_equity_point(10050)

    snap = store.snapshot()
    assert len(snap["equity_curve"]) == 2
    assert snap["equity_curve"][1]["value"] == 10050


def test_snapshot_is_deep_copy():
    store = StateStore()
    store.update(status="running")
    snap1 = store.snapshot()
    snap1["status"] = "modified"
    snap2 = store.snapshot()
    assert snap2["status"] == "running"


def test_server_app_exists():
    from agent.server import app
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/" in rules
    assert "/api/state" in rules
