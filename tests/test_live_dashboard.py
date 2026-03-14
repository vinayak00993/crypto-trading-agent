"""Tests for the shared state store and live dashboard server."""

from agent.state import StateStore


def test_state_store_update():
    """State store should accept and return updates."""
    store = StateStore()
    store.update(status="running", tick=5)

    snap = store.snapshot()
    assert snap["status"] == "running"
    assert snap["tick"] == 5
    assert snap["last_updated"] is not None


def test_state_store_add_signal():
    """Signals should be appended to the list."""
    store = StateStore()
    store.add_signal({"pair": "BTC/USDT", "signal": "BUY", "confidence": 0.7})
    store.add_signal({"pair": "ETH/USDT", "signal": "HOLD", "confidence": 0.3})

    snap = store.snapshot()
    assert len(snap["signals"]) == 2
    assert snap["signals"][0]["pair"] == "BTC/USDT"


def test_state_store_add_trade():
    """Trades should be appended to the trade log."""
    store = StateStore()
    store.add_trade({"pair": "BTC/USDT", "side": "BUY", "price": 50000})

    snap = store.snapshot()
    assert len(snap["trade_log"]) == 1
    assert snap["trade_log"][0]["side"] == "BUY"


def test_state_store_equity_curve():
    """Equity points should be tracked."""
    store = StateStore()
    store.add_equity_point(10000)
    store.add_equity_point(10050)
    store.add_equity_point(10025)

    snap = store.snapshot()
    assert len(snap["equity_curve"]) == 3
    assert snap["equity_curve"][1]["value"] == 10050


def test_state_store_signals_capped_at_100():
    """Signal list should be capped at 100 entries."""
    store = StateStore()
    for i in range(150):
        store.add_signal({"pair": f"PAIR_{i}", "signal": "HOLD"})

    snap = store.snapshot()
    assert len(snap["signals"]) == 100


def test_state_store_snapshot_is_copy():
    """Snapshot should return a deep copy, not a reference."""
    store = StateStore()
    store.update(status="running")

    snap1 = store.snapshot()
    snap1["status"] = "modified"

    snap2 = store.snapshot()
    assert snap2["status"] == "running"  # original unchanged


def test_server_app_exists():
    """The Flask app should be importable and have routes."""
    from agent.server import app
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/" in rules
    assert "/api/state" in rules
