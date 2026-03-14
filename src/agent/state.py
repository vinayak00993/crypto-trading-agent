"""
Shared State Store — thread-safe state that bridges the agent loop and the dashboard.

The agent loop writes state after every tick. The dashboard web server
reads it to serve real-time data to the browser.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any


class StateStore:
    """
    Thread-safe container for the agent's current state.

    The agent loop calls `update()` after each tick.
    The web server calls `snapshot()` to read the latest state.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "status": "starting",
            "tick": 0,
            "last_updated": None,
            "mode": "paper",
            "exchange": "",
            "strategy": "",
            "timeframe": "",
            "pairs": [],
            "prices": {},
            "portfolio": {
                "cash": 0,
                "total_value": 0,
                "total_pnl": 0,
                "total_pnl_pct": 0,
                "open_positions": 0,
                "total_trades": 0,
                "positions": {},
            },
            "signals": [],       # Recent signals from the strategy
            "trade_log": [],     # All executed trades
            "equity_curve": [],  # Portfolio value over time
        }

    def update(self, **kwargs: Any) -> None:
        """Update state fields (thread-safe)."""
        with self._lock:
            for key, value in kwargs.items():
                self._state[key] = value
            self._state["last_updated"] = datetime.now(timezone.utc).isoformat()

    def add_signal(self, signal: dict[str, Any]) -> None:
        """Append a strategy signal to the log (keeps last 100)."""
        with self._lock:
            self._state["signals"].append(signal)
            self._state["signals"] = self._state["signals"][-100:]

    def add_trade(self, trade: dict[str, Any]) -> None:
        """Append an executed trade to the log."""
        with self._lock:
            self._state["trade_log"].append(trade)

    def add_equity_point(self, value: float) -> None:
        """Append a portfolio value snapshot (keeps last 1000)."""
        with self._lock:
            self._state["equity_curve"].append({
                "time": datetime.now(timezone.utc).isoformat(),
                "value": round(value, 2),
            })
            self._state["equity_curve"] = self._state["equity_curve"][-1000:]

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of the full state (thread-safe)."""
        with self._lock:
            import copy
            return copy.deepcopy(self._state)


# Global singleton — shared between agent thread and web server thread
store = StateStore()
