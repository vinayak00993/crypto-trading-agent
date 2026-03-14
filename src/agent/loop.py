"""
Multi-Pod Agent Loop — runs 4 independent strategies with equal capital.

Each "pod" is an independent strategy + executor + portfolio manager.
All pods share the same market data feed but trade with their own capital.
The dashboard shows combined and per-strategy performance.

Architecture:
  $10,000 total → $2,500 per pod
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │ SMA Crossover│ │     RSI      │ │    MACD      │ │  Bollinger   │
  │   $2,500     │ │   $2,500     │ │   $2,500     │ │   $2,500     │
  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog

from agent.config import AgentConfig
from agent.strategies.base import Signal, BaseStrategy
from agent.strategies.loader import load_strategy, STRATEGY_REGISTRY
from agent.state import store
from market_data.feed import MarketDataFeed
from execution.paper import PaperExecutor, OrderStatus
from portfolio.manager import PortfolioManager

log = structlog.get_logger()


@dataclass
class Pod:
    """An independent strategy pod with its own capital."""
    name: str
    strategy: BaseStrategy
    executor: PaperExecutor
    portfolio: PortfolioManager


class AgentLoop:
    """
    Multi-pod orchestrator — runs all strategies simultaneously.

    Parameters
    ----------
    cfg : AgentConfig
        The full, validated agent configuration.
    """

    def __init__(self, cfg: AgentConfig) -> None:
        self.cfg = cfg
        self.tick_count: int = 0

        # Shared market data feed
        self.feed = MarketDataFeed(cfg.exchange, cfg.trading)

        # Build pods from all groups: Technical + Fundamental + ML
        from agent.strategies.loader import TECHNICAL_STRATEGIES, FUNDAMENTAL_STRATEGIES, ML_STRATEGIES

        capital_per_pod = 2500.0  # fixed $2,500 per pod

        self.pods: list[Pod] = []
        self.ml_pod: Pod | None = None  # reference to the ML pod for feeding signals

        # Technical pods ($2,500 each)
        for strategy_name in TECHNICAL_STRATEGIES:
            strategy = load_strategy(strategy_name, cfg.strategy.params)
            executor = PaperExecutor(capital_per_pod)
            portfolio = PortfolioManager(cfg.risk, executor)
            self.pods.append(Pod(
                name=strategy_name,
                strategy=strategy,
                executor=executor,
                portfolio=portfolio,
            ))

        # Fundamental pods ($2,500 each)
        for strategy_name in FUNDAMENTAL_STRATEGIES:
            strategy = load_strategy(strategy_name, cfg.strategy.params)
            executor = PaperExecutor(capital_per_pod)
            portfolio = PortfolioManager(cfg.risk, executor)
            self.pods.append(Pod(
                name=strategy_name,
                strategy=strategy,
                executor=executor,
                portfolio=portfolio,
            ))

        # ML Meta-Learner pod ($2,500)
        for strategy_name in ML_STRATEGIES:
            strategy = load_strategy(strategy_name, cfg.strategy.params)
            executor = PaperExecutor(capital_per_pod)
            portfolio = PortfolioManager(cfg.risk, executor)
            ml_pod = Pod(
                name=strategy_name,
                strategy=strategy,
                executor=executor,
                portfolio=portfolio,
            )
            self.pods.append(ml_pod)
            self.ml_pod = ml_pod

        self.total_starting_balance = capital_per_pod * len(self.pods)

        # Initialize shared state
        store.update(
            status="initializing",
            mode=cfg.mode,
            exchange=cfg.exchange.name,
            strategy="multi_pod_9",
            timeframe=cfg.trading.default_timeframe,
            pairs=cfg.trading.pairs,
        )

        log.info(
            "agent_loop.pods_created",
            num_pods=len(self.pods),
            capital_per_pod=capital_per_pod,
            technical=[p.name for p in self.pods if p.name in TECHNICAL_STRATEGIES],
            fundamental=[p.name for p in self.pods if p.name in FUNDAMENTAL_STRATEGIES],
            ml=[p.name for p in self.pods if p.name in ML_STRATEGIES],
            total_capital=self.total_starting_balance,
        )

    def start(self) -> None:
        """Connect to the exchange and begin the loop."""
        log.info(
            "agent_loop.starting",
            strategies=[p.name for p in self.pods],
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
        """Execute one cycle across all pods."""
        self.tick_count += 1
        log.info("agent_loop.tick", tick=self.tick_count)

        # Step 1: Fetch current prices (shared across all pods)
        current_prices = self.feed.get_all_prices()
        if not current_prices:
            log.warning("agent_loop.no_prices", msg="Could not fetch prices, skipping tick")
            return

        store.update(prices=current_prices, tick=self.tick_count)

        # Step 2: Fetch candles once (shared across all pods)
        max_history = max(p.strategy.required_history for p in self.pods) + 10
        all_candles = self.feed.fetch_all_pairs(limit=max_history)

        # Step 3: Run non-ML pods first, collect signals for the meta-learner
        from agent.strategies.ml_meta_learner import MLMetaLearner

        for pod in self.pods:
            if isinstance(pod.strategy, MLMetaLearner):
                continue  # run ML pod last
            self._run_pod(pod, current_prices, all_candles)

        # Step 4: Feed all signals to the ML meta-learner
        if self.ml_pod and isinstance(self.ml_pod.strategy, MLMetaLearner):
            ml: MLMetaLearner = self.ml_pod.strategy

            # Feed current prices
            for pair, price in current_prices.items():
                ml.record_price(pair, price, self.tick_count)

            # Feed recent signals from other pods
            snapshot = store.snapshot()
            for sig in snapshot.get("signals", []):
                pod_name = sig.get("pod", "")
                if pod_name and pod_name != "ml_meta_learner":
                    pair = sig.get("pair", "")
                    signal = sig.get("signal", "HOLD")
                    price = current_prices.get(pair, 0)
                    if price > 0:
                        ml.record_signal(pod_name, pair, signal, price, self.tick_count)

            # Now run the ML pod
            self._run_pod(self.ml_pod, current_prices, all_candles)

            # Log ML phase and rankings
            rankings = ml.get_pod_rankings()
            if rankings:
                top3 = rankings[:3]
                log.info(
                    "ml.status",
                    phase=ml.phase,
                    tick=self.tick_count,
                    top_pods=[(r["name"], f"{r['accuracy']}%", f"w={r['weight']}") for r in top3],
                    pending_evals=len(ml._pending_evals),
                )

        # Step 5: Update combined portfolio state
        self._update_combined_state(current_prices)

    def _run_pod(
        self,
        pod: Pod,
        current_prices: dict[str, float],
        all_candles: dict[str, Any],
    ) -> None:
        """Run a single strategy pod for one tick."""

        # Check stop-loss / take-profit
        closed = pod.portfolio.check_stop_loss_take_profit(current_prices)
        if closed:
            log.info("pod.auto_closed", pod=pod.name, pairs=closed)
            for pair in closed:
                last_order = pod.executor.order_history[-1] if pod.executor.order_history else None
                if last_order:
                    store.add_trade({
                        "time": datetime.now(timezone.utc).isoformat(),
                        "pod": pod.name,
                        "pair": pair,
                        "side": "SELL",
                        "price": last_order.price,
                        "cost": round(last_order.cost, 2),
                        "reason": f"[{pod.name}] {last_order.reason}",
                        "status": "FILLED",
                    })

        # Run strategy on each pair
        for pair, candles in all_candles.items():
            if candles.empty:
                continue

            rec = pod.strategy.evaluate(pair, candles)

            log.info(
                "pod.signal",
                pod=pod.name,
                pair=pair,
                signal=rec.signal.value,
                confidence=rec.confidence,
                reason=rec.reason[:80],
            )

            store.add_signal({
                "time": datetime.now(timezone.utc).isoformat(),
                "pod": pod.name,
                "pair": pair,
                "signal": rec.signal.value,
                "confidence": rec.confidence,
                "reason": f"[{pod.name}] {rec.reason}",
            })

            # Execute signals
            if rec.signal == Signal.BUY and rec.confidence >= 0.5:
                price = current_prices.get(pair, 0)
                if price > 0:
                    filled = pod.portfolio.try_buy(
                        pair=pair, price=price,
                        current_prices=current_prices,
                        reason=f"[{pod.name}] {rec.reason}",
                    )
                    if filled:
                        last_order = pod.executor.order_history[-1]
                        store.add_trade({
                            "time": datetime.now(timezone.utc).isoformat(),
                            "pod": pod.name,
                            "pair": pair,
                            "side": "BUY",
                            "price": price,
                            "quantity": round(last_order.quantity, 8),
                            "cost": round(last_order.cost, 2),
                            "reason": f"[{pod.name}] {rec.reason}",
                            "status": "FILLED",
                        })

            elif rec.signal == Signal.SELL and rec.confidence >= 0.5:
                price = current_prices.get(pair, 0)
                if price > 0:
                    filled = pod.portfolio.try_sell(
                        pair=pair, price=price,
                        reason=f"[{pod.name}] {rec.reason}",
                    )
                    if filled:
                        last_order = pod.executor.order_history[-1]
                        store.add_trade({
                            "time": datetime.now(timezone.utc).isoformat(),
                            "pod": pod.name,
                            "pair": pair,
                            "side": "SELL",
                            "price": price,
                            "quantity": round(last_order.quantity, 8),
                            "cost": round(last_order.cost, 2),
                            "reason": f"[{pod.name}] {rec.reason}",
                            "status": "FILLED",
                        })

        # Update pod-specific state
        pod_summary = pod.executor.summary(current_prices)
        pod_value = pod.executor.total_value(current_prices)

        store.update_pod(pod.name, {
            "strategy": pod.name,
            "cash": round(pod.executor.cash, 2),
            "total_value": round(pod_value, 2),
            "starting_balance": round(pod.executor.starting_balance, 2),
            "pnl": round(pod_value - pod.executor.starting_balance, 2),
            "pnl_pct": round(((pod_value - pod.executor.starting_balance) / pod.executor.starting_balance) * 100, 2),
            "total_trades": len(pod.executor.order_history),
            "open_positions": len(pod.executor.positions),
            "positions": pod_summary.get("positions", {}),
        })

        store.add_pod_equity_point(pod.name, pod_value)

    def _update_combined_state(self, current_prices: dict[str, float]) -> None:
        """Aggregate all pod values into the combined portfolio view."""
        total_value = sum(p.executor.total_value(current_prices) for p in self.pods)
        total_cash = sum(p.executor.cash for p in self.pods)
        total_positions = sum(len(p.executor.positions) for p in self.pods)
        total_trades = sum(len(p.executor.order_history) for p in self.pods)
        total_pnl = total_value - self.total_starting_balance
        total_pnl_pct = (total_pnl / self.total_starting_balance) * 100

        # Merge all positions
        all_positions = {}
        for pod in self.pods:
            for pair, pos_data in pod.executor.summary(current_prices).get("positions", {}).items():
                key = f"{pair} ({pod.name})"
                all_positions[key] = pos_data

        combined = {
            "cash": round(total_cash, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "open_positions": total_positions,
            "total_trades": total_trades,
            "positions": all_positions,
        }

        store.update(portfolio=combined)
        store.add_equity_point(total_value)

        log.info(
            "agent_loop.portfolio",
            total_value=combined["total_value"],
            pnl=combined["total_pnl"],
            pnl_pct=combined["total_pnl_pct"],
            positions=combined["open_positions"],
            trades=combined["total_trades"],
            pod_values={p.name: round(p.executor.total_value(current_prices), 2) for p in self.pods},
        )

    def _print_final_summary(self) -> None:
        """Print a final report when the agent shuts down."""
        current_prices = self.feed.get_all_prices()

        print("\n" + "=" * 70)
        print("  MULTI-POD FINAL REPORT")
        print("=" * 70)
        print(f"  Total ticks: {self.tick_count}")
        print(f"  Starting balance: ${self.total_starting_balance:,.2f}")
        print()

        total_value = 0
        for pod in self.pods:
            value = pod.executor.total_value(current_prices)
            pnl = value - pod.executor.starting_balance
            pnl_pct = (pnl / pod.executor.starting_balance) * 100
            trades = len(pod.executor.order_history)
            total_value += value

            emoji = "+" if pnl >= 0 else ""
            print(f"  {pod.name:<20} ${value:>10,.2f}  ({emoji}{pnl_pct:.2f}%)  {trades} trades")

        total_pnl = total_value - self.total_starting_balance
        total_pnl_pct = (total_pnl / self.total_starting_balance) * 100
        print("-" * 70)
        emoji = "+" if total_pnl >= 0 else ""
        print(f"  {'COMBINED':<20} ${total_value:>10,.2f}  ({emoji}{total_pnl_pct:.2f}%)")
        print("=" * 70 + "\n")
