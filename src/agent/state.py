"""
Shared State Store — thread-safe state that bridges the agent loop and the dashboard.

Supports multi-pod architecture: tracks combined portfolio AND per-strategy pod data.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any


class StateStore:
    """
    Thread-safe container for the agent's current state.

    The agent loop calls update methods after each tick.
    The web server calls snapshot() to read the latest state.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "status": "starting",
            "tick": 0,
            "last_updated": None,
            "mode": "paper",
            "exchange": "",
            "strategy": "multi_pod",
            "timeframe": "",
            "pairs": [],
            "prices": {},
            # Combined portfolio (sum of all pods)
            "portfolio": {
                "cash": 0,
                "total_value": 0,
                "total_pnl": 0,
                "total_pnl_pct": 0,
                "open_positions": 0,
                "total_trades": 0,
                "positions": {},
            },
            # Per-strategy pod data
            "pods": {},           # {strategy_name: {value, pnl, pnl_pct, trades, positions, ...}}
            "pod_equity": {},     # {strategy_name: [{time, value}, ...]}
            "signals": [],        # Recent signals from all strategies
            "trade_log": [],      # All executed trades (tagged with strategy)
            "equity_curve": [],   # Combined portfolio value over time
        }

    def update(self, **kwargs: Any) -> None:
        """Update state fields (thread-safe)."""
        with self._lock:
            for key, value in kwargs.items():
                self._state[key] = value
            self._state["last_updated"] = datetime.now(timezone.utc).isoformat()

    def update_pod(self, pod_name: str, pod_data: dict[str, Any]) -> None:
        """Update a single pod's state."""
        with self._lock:
            self._state["pods"][pod_name] = pod_data

    def add_pod_equity_point(self, pod_name: str, value: float) -> None:
        """Track equity for a specific pod."""
        with self._lock:
            if pod_name not in self._state["pod_equity"]:
                self._state["pod_equity"][pod_name] = []
            self._state["pod_equity"][pod_name].append({
                "time": datetime.now(timezone.utc).isoformat(),
                "value": round(value, 2),
            })
            self._state["pod_equity"][pod_name] = self._state["pod_equity"][pod_name][-500:]

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
        """Append a combined portfolio value snapshot."""
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


# Global singleton
store = StateStore()
