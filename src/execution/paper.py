"""
Paper Trading Executor — simulates trade execution without real money.

Keeps an in-memory ledger of balances and positions. Fills orders
instantly at the current market price (no slippage simulation yet).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger()


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass
class Order:
    """Record of an executed (or rejected) order."""
    id: str
    pair: str
    side: OrderSide
    quantity: float
    price: float
    cost: float                     # quantity × price
    status: OrderStatus
    reason: str                     # Why the trade was made (from strategy)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Position:
    """An open position in a single trading pair."""
    pair: str
    quantity: float
    entry_price: float
    entry_time: datetime

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.entry_price

    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.quantity

    def unrealized_pnl_pct(self, current_price: float) -> float:
        if self.entry_price == 0:
            return 0.0
        return ((current_price - self.entry_price) / self.entry_price) * 100


class PaperExecutor:
    """
    Simulates trade execution using fake money.

    Parameters
    ----------
    starting_balance : float
        How much simulated capital to start with (in base currency like USDT).
    """

    def __init__(self, starting_balance: float = 10_000.0) -> None:
        self.starting_balance = starting_balance
        self.cash: float = starting_balance
        self.positions: dict[str, Position] = {}       # pair → Position
        self.order_history: list[Order] = []
        self._order_counter: int = 0

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------
    def buy(self, pair: str, amount_usd: float, price: float, reason: str = "") -> Order:
        """
        Buy into a position.

        Parameters
        ----------
        pair : str
            e.g. "BTC/USDT"
        amount_usd : float
            How much cash to spend (in base currency).
        price : float
            Current market price to simulate the fill at.
        reason : str
            Human-readable explanation from the strategy.

        Returns
        -------
        Order
        """
        self._order_counter += 1
        order_id = f"PAPER-{self._order_counter:06d}"

        # Check if we have enough cash
        if amount_usd > self.cash:
            order = Order(
                id=order_id,
                pair=pair,
                side=OrderSide.BUY,
                quantity=0,
                price=price,
                cost=0,
                status=OrderStatus.REJECTED,
                reason=f"Insufficient funds: need ${amount_usd:.2f}, have ${self.cash:.2f}",
            )
            log.warning("executor.order_rejected", **self._order_log(order))
            self.order_history.append(order)
            return order

        quantity = amount_usd / price
        self.cash -= amount_usd

        # Add to existing position or create new one
        if pair in self.positions:
            pos = self.positions[pair]
            total_qty = pos.quantity + quantity
            avg_price = (pos.cost_basis + amount_usd) / total_qty
            pos.quantity = total_qty
            pos.entry_price = avg_price
        else:
            self.positions[pair] = Position(
                pair=pair,
                quantity=quantity,
                entry_price=price,
                entry_time=datetime.now(timezone.utc),
            )

        order = Order(
            id=order_id,
            pair=pair,
            side=OrderSide.BUY,
            quantity=quantity,
            price=price,
            cost=amount_usd,
            status=OrderStatus.FILLED,
            reason=reason,
        )

        log.info("executor.buy_filled", **self._order_log(order))
        self.order_history.append(order)
        return order

    def sell(self, pair: str, price: float, reason: str = "") -> Order:
        """
        Sell an entire position.

        Parameters
        ----------
        pair : str
            The pair to close.
        price : float
            Current market price to simulate the fill at.
        reason : str
            Human-readable explanation.

        Returns
        -------
        Order
        """
        self._order_counter += 1
        order_id = f"PAPER-{self._order_counter:06d}"

        if pair not in self.positions:
            order = Order(
                id=order_id,
                pair=pair,
                side=OrderSide.SELL,
                quantity=0,
                price=price,
                cost=0,
                status=OrderStatus.REJECTED,
                reason=f"No open position for {pair}",
            )
            log.warning("executor.order_rejected", **self._order_log(order))
            self.order_history.append(order)
            return order

        pos = self.positions.pop(pair)
        proceeds = pos.quantity * price
        pnl = proceeds - pos.cost_basis
        self.cash += proceeds

        order = Order(
            id=order_id,
            pair=pair,
            side=OrderSide.SELL,
            quantity=pos.quantity,
            price=price,
            cost=proceeds,
            status=OrderStatus.FILLED,
            reason=reason,
        )

        log.info(
            "executor.sell_filled",
            pnl=round(pnl, 2),
            pnl_pct=round((pnl / pos.cost_basis) * 100, 2) if pos.cost_basis else 0,
            **self._order_log(order),
        )
        self.order_history.append(order)
        return order

    # ------------------------------------------------------------------
    # Portfolio summary
    # ------------------------------------------------------------------
    def total_value(self, current_prices: dict[str, float]) -> float:
        """Calculate total portfolio value: cash + all open positions."""
        position_value = sum(
            pos.quantity * current_prices.get(pair, pos.entry_price)
            for pair, pos in self.positions.items()
        )
        return self.cash + position_value

    def summary(self, current_prices: dict[str, float]) -> dict[str, Any]:
        """Return a snapshot of the portfolio state."""
        total = self.total_value(current_prices)
        return {
            "cash": round(self.cash, 2),
            "total_value": round(total, 2),
            "total_pnl": round(total - self.starting_balance, 2),
            "total_pnl_pct": round(((total - self.starting_balance) / self.starting_balance) * 100, 2),
            "open_positions": len(self.positions),
            "total_trades": len(self.order_history),
            "positions": {
                pair: {
                    "quantity": round(pos.quantity, 8),
                    "entry_price": round(pos.entry_price, 2),
                    "current_price": round(current_prices.get(pair, 0), 2),
                    "unrealized_pnl": round(pos.unrealized_pnl(current_prices.get(pair, pos.entry_price)), 2),
                    "unrealized_pnl_pct": round(pos.unrealized_pnl_pct(current_prices.get(pair, pos.entry_price)), 2),
                }
                for pair, pos in self.positions.items()
            },
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _order_log(self, order: Order) -> dict[str, Any]:
        return {
            "order_id": order.id,
            "pair": order.pair,
            "side": order.side.value,
            "quantity": round(order.quantity, 8),
            "price": round(order.price, 2),
            "cost": round(order.cost, 2),
            "status": order.status.value,
            "cash_remaining": round(self.cash, 2),
        }
