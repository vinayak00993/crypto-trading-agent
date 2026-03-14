"""
Agent Loop — the main orchestrator.

On each tick:
  1. Fetch fresh candle data
  2. Check stop-loss / take-profit on open positions
  3. Run the strategy on each pair
  4. Execute any BUY/SELL signals through the portfolio manager
  5. Update shared state for the live dashboard
  6. Log the portfolio summary
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import structlog

from agent.config import AgentConfig
from agent.strategies.base import Signal, BaseStrategy
from agent.strategies.loader import load_strategy
from agent.state import store
from market_data.feed import MarketDataFeed
from execution.paper import PaperExecutor, OrderStatus
from portfolio.manager import PortfolioManager

log = structlog.get_logger()


class AgentLoop:
    """
    Wires all components together and runs the trading loop.

    Parameters
    ----------
    cfg : AgentConfig
        The full, validated agent configuration.
    """

    def __init__(self, cfg: AgentConfig) -> None:
        self.cfg = cfg
        self.tick_count: int = 0

        # Build components
        self.feed = MarketDataFeed(cfg.exchange, cfg.trading)
        self.strategy: BaseStrategy = load_strategy(cfg.strategy.name, cfg.strategy.params)
        self.executor = PaperExecutor(cfg.paper.starting_balance)
        self.portfolio = PortfolioManager(cfg.risk, self.executor)

        # Initialize shared state
        store.update(
            status="initializing",
            mode=cfg.mode,
            exchange=cfg.exchange.name,
            strategy=cfg.strategy.name,
            timeframe=cfg.trading.default_timeframe,
            pairs=cfg.trading.pairs,
        )

    def start(self) -> None:
        """Connect to the exchange and begin the loop."""
        log.info(
            "agent_loop.starting",
            strategy=self.strategy.name,
            pairs=self.cfg.trading.pairs,
            interval_s=self.cfg.scheduler.strategy_interval_seconds,
            mode=self.cfg.mode,
        )

        self.feed.connect()
        store.update(status="running")

        log.info("agent_loop.running", msg="Agent is live. Press Ctrl+C to stop.")

        try:
            while True:
                self._tick()
                time.sleep(self.cfg.scheduler.strategy_interval_seconds)
        except KeyboardInterrupt:
            store.update(status="stopped")
            log.info("agent_loop.stopped", msg="Shutdown by user (Ctrl+C)")
            self._print_final_summary()

    def _tick(self) -> None:
        """Execute one cycle of the trading loop."""
        self.tick_count += 1
        log.info("agent_loop.tick", tick=self.tick_count)

        # Step 1: Fetch current prices
        current_prices = self.feed.get_all_prices()
        if not current_prices:
            log.warning("agent_loop.no_prices", msg="Could not fetch prices, skipping tick")
            return

        store.update(prices=current_prices, tick=self.tick_count)

        # Step 2: Check stop-loss / take-profit
        closed = self.portfolio.check_stop_loss_take_profit(current_prices)
        if closed:
            log.info("agent_loop.auto_closed", pairs=closed)
            for pair in closed:
                last_order = self.executor.order_history[-1] if self.executor.order_history else None
                if last_order:
                    store.add_trade({
                        "time": datetime.now(timezone.utc).isoformat(),
                        "pair": pair,
                        "side": "SELL",
                        "price": last_order.price,
                        "cost": round(last_order.cost, 2),
                        "reason": last_order.reason,
                        "status": "FILLED",
                    })

        # Step 3: Fetch candles and run strategy
        all_candles = self.feed.fetch_all_pairs(limit=self.strategy.required_history + 10)

        for pair, candles in all_candles.items():
            if candles.empty:
                continue

            recommendation = self.strategy.evaluate(pair, candles)

            log.info(
                "agent_loop.signal",
                pair=pair,
                signal=recommendation.signal.value,
                confidence=recommendation.confidence,
                reason=recommendation.reason,
            )

            store.add_signal({
                "time": datetime.now(timezone.utc).isoformat(),
                "pair": pair,
                "signal": recommendation.signal.value,
                "confidence": recommendation.confidence,
                "reason": recommendation.reason,
                "metadata": recommendation.metadata,
            })

            # Step 4: Execute signals
            if recommendation.signal == Signal.BUY:
                price = current_prices.get(pair, 0)
                if price > 0:
                    filled = self.portfolio.try_buy(
                        pair=pair, price=price,
                        current_prices=current_prices,
                        reason=recommendation.reason,
                    )
                    if filled:
                        last_order = self.executor.order_history[-1]
                        store.add_trade({
                            "time": datetime.now(timezone.utc).isoformat(),
                            "pair": pair, "side": "BUY",
                            "price": price,
                            "quantity": round(last_order.quantity, 8),
                            "cost": round(last_order.cost, 2),
                            "reason": recommendation.reason,
                            "status": "FILLED",
                        })

            elif recommendation.signal == Signal.SELL:
                price = current_prices.get(pair, 0)
                if price > 0:
                    filled = self.portfolio.try_sell(
                        pair=pair, price=price,
                        reason=recommendation.reason,
                    )
                    if filled:
                        last_order = self.executor.order_history[-1]
                        store.add_trade({
                            "time": datetime.now(timezone.utc).isoformat(),
                            "pair": pair, "side": "SELL",
                            "price": price,
                            "quantity": round(last_order.quantity, 8),
                            "cost": round(last_order.cost, 2),
                            "reason": recommendation.reason,
                            "status": "FILLED",
                        })

        # Step 5: Update shared state
        summary = self.executor.summary(current_prices)
        store.update(portfolio=summary)
        store.add_equity_point(summary["total_value"])

        log.info(
            "agent_loop.portfolio",
            cash=summary["cash"],
            total_value=summary["total_value"],
            pnl=summary["total_pnl"],
            pnl_pct=summary["total_pnl_pct"],
            open_positions=summary["open_positions"],
            total_trades=summary["total_trades"],
        )

    def _print_final_summary(self) -> None:
        """Print a final report when the agent shuts down."""
        current_prices = self.feed.get_all_prices()
        summary = self.executor.summary(current_prices)

        log.info("=" * 60)
        log.info("agent_loop.final_report")
        log.info(f"  Total ticks:      {self.tick_count}")
        log.info(f"  Total trades:     {summary['total_trades']}")
        log.info(f"  Starting balance: ${self.executor.starting_balance:,.2f}")
        log.info(f"  Final value:      ${summary['total_value']:,.2f}")
        log.info(f"  P&L:              ${summary['total_pnl']:,.2f} ({summary['total_pnl_pct']:.2f}%)")
        log.info(f"  Cash remaining:   ${summary['cash']:,.2f}")
        log.info(f"  Open positions:   {summary['open_positions']}")
        log.info("=" * 60)
