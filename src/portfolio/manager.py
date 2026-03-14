"""
Portfolio Manager — enforces risk limits and manages position sizing.

Acts as a safety layer between the strategy's signals and the executor.
Even if a strategy says BUY, the portfolio manager can veto the trade
if it would violate risk limits.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from agent.config import RiskConfig
from execution.paper import PaperExecutor, OrderSide, OrderStatus

log = structlog.get_logger()


class PortfolioManager:
    """
    Wraps the executor and applies risk management rules before every trade.

    Parameters
    ----------
    risk_cfg : RiskConfig
        Max position sizes, stop-loss, daily loss limits.
    executor : PaperExecutor
        The executor that actually fills orders.
    """

    def __init__(self, risk_cfg: RiskConfig, executor: PaperExecutor) -> None:
        self.risk = risk_cfg
        self.executor = executor
        self._daily_starting_value: float = executor.starting_balance
        self._day_start: datetime = datetime.now(timezone.utc)
        self._halted: bool = False

    # ------------------------------------------------------------------
    # Risk checks
    # ------------------------------------------------------------------
    def _check_daily_loss(self, current_prices: dict[str, float]) -> bool:
        """Return True if we've exceeded the max daily loss limit."""
        now = datetime.now(timezone.utc)

        # Reset daily tracker at midnight UTC
        if now.date() > self._day_start.date():
            self._daily_starting_value = self.executor.total_value(current_prices)
            self._day_start = now
            self._halted = False

        current_value = self.executor.total_value(current_prices)
        daily_pnl_pct = ((current_value - self._daily_starting_value) / self._daily_starting_value) * 100

        if daily_pnl_pct <= -self.risk.max_daily_loss_pct:
            log.error(
                "risk.daily_loss_limit_hit",
                daily_pnl_pct=round(daily_pnl_pct, 2),
                limit=self.risk.max_daily_loss_pct,
            )
            self._halted = True
            return True
        return False

    def _check_max_positions(self) -> bool:
        """Return True if we've hit the max number of open positions."""
        return len(self.executor.positions) >= self.risk.max_open_positions

    def _calculate_position_size(self, current_prices: dict[str, float]) -> float:
        """Calculate how much cash to use for a single trade based on risk limits."""
        total_value = self.executor.total_value(current_prices)
        max_spend = total_value * (self.risk.max_position_pct / 100)
        # Don't spend more than we have in cash
        return min(max_spend, self.executor.cash)

    # ------------------------------------------------------------------
    # Trade execution with risk management
    # ------------------------------------------------------------------
    def try_buy(
        self,
        pair: str,
        price: float,
        current_prices: dict[str, float],
        reason: str = "",
    ) -> bool:
        """
        Attempt to open a position, subject to all risk checks.

        Returns True if the order was filled, False if rejected.
        """
        # Kill switch
        if self._halted:
            log.warning("risk.trading_halted", pair=pair, msg="Daily loss limit exceeded")
            return False

        if self._check_daily_loss(current_prices):
            return False

        # Already have a position in this pair?
        if pair in self.executor.positions:
            log.debug("risk.already_positioned", pair=pair)
            return False

        # Max positions check
        if self._check_max_positions():
            log.warning(
                "risk.max_positions_reached",
                pair=pair,
                limit=self.risk.max_open_positions,
            )
            return False

        # Calculate safe position size
        amount = self._calculate_position_size(current_prices)
        if amount < 1.0:  # minimum trade size
            log.warning("risk.insufficient_funds", pair=pair, available=round(amount, 2))
            return False

        order = self.executor.buy(pair, amount, price, reason)
        return order.status == OrderStatus.FILLED

    def try_sell(
        self,
        pair: str,
        price: float,
        reason: str = "",
    ) -> bool:
        """
        Attempt to close a position.

        Returns True if the order was filled, False if rejected.
        """
        order = self.executor.sell(pair, price, reason)
        return order.status == OrderStatus.FILLED

    # ------------------------------------------------------------------
    # Stop-loss / take-profit checks
    # ------------------------------------------------------------------
    def check_stop_loss_take_profit(self, current_prices: dict[str, float]) -> list[str]:
        """
        Check all open positions for stop-loss or take-profit triggers.

        Returns a list of pairs that were closed.
        """
        closed: list[str] = []

        # Iterate over a copy since we might modify positions during iteration
        for pair, pos in list(self.executor.positions.items()):
            current_price = current_prices.get(pair)
            if current_price is None:
                continue

            pnl_pct = pos.unrealized_pnl_pct(current_price)

            # Stop-loss
            if pnl_pct <= -self.risk.stop_loss_pct:
                log.warning(
                    "risk.stop_loss_triggered",
                    pair=pair,
                    pnl_pct=round(pnl_pct, 2),
                    limit=self.risk.stop_loss_pct,
                )
                self.try_sell(pair, current_price, reason=f"Stop-loss at {pnl_pct:.1f}%")
                closed.append(pair)

            # Take-profit
            elif pnl_pct >= self.risk.take_profit_pct:
                log.info(
                    "risk.take_profit_triggered",
                    pair=pair,
                    pnl_pct=round(pnl_pct, 2),
                    limit=self.risk.take_profit_pct,
                )
                self.try_sell(pair, current_price, reason=f"Take-profit at {pnl_pct:.1f}%")
                closed.append(pair)

        return closed
