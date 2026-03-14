"""
Backtesting Engine — runs a strategy against historical candle data.

Simulates the full trading loop offline: for each candle, the engine
runs the strategy, executes paper trades, enforces risk limits, and
tracks every trade. At the end it calculates performance metrics like
Sharpe ratio, max drawdown, win rate, etc.

Usage:
    python -m agent.backtest                         # uses defaults
    python -m agent.backtest --strategy rsi           # test RSI strategy
    python -m agent.backtest --pair BTC/USDT --days 90
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
import structlog

from agent.config import AgentConfig, RiskConfig
from agent.strategies.base import BaseStrategy, Signal
from agent.strategies.loader import load_strategy
from execution.paper import PaperExecutor, OrderStatus

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Trade record for backtest results
# ---------------------------------------------------------------------------
@dataclass
class BacktestTrade:
    pair: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime | None = None
    exit_price: float | None = None
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    reason_entry: str = ""
    reason_exit: str = ""


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------
@dataclass
class PerformanceMetrics:
    """All the stats you'd want to see after a backtest."""
    total_return_pct: float = 0.0
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    avg_holding_period: str = ""
    start_date: str = ""
    end_date: str = ""
    starting_balance: float = 0.0
    ending_balance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------
class Backtester:
    """
    Runs a strategy against historical data and produces performance metrics.

    Parameters
    ----------
    strategy : BaseStrategy
        The strategy to test.
    starting_balance : float
        Simulated capital.
    risk_cfg : RiskConfig
        Risk management settings.
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        starting_balance: float = 10_000.0,
        risk_cfg: RiskConfig | None = None,
    ) -> None:
        self.strategy = strategy
        self.starting_balance = starting_balance
        self.risk_cfg = risk_cfg or RiskConfig()

    def run(self, pair: str, candles: pd.DataFrame) -> BacktestResult:
        """
        Run the strategy on a full set of historical candles.

        Parameters
        ----------
        pair : str
            Trading pair, e.g. "BTC/USDT".
        candles : pd.DataFrame
            Full OHLCV history. Must have columns: open, high, low, close, volume.

        Returns
        -------
        BacktestResult
        """
        executor = PaperExecutor(self.starting_balance)
        trades: list[BacktestTrade] = []
        equity_curve: list[float] = []
        open_trade: BacktestTrade | None = None

        min_candles = self.strategy.required_history + 2
        max_position_usd = self.starting_balance * (self.risk_cfg.max_position_pct / 100)

        log.info(
            "backtest.start",
            strategy=self.strategy.name,
            pair=pair,
            candles=len(candles),
            min_required=min_candles,
        )

        for i in range(min_candles, len(candles)):
            window = candles.iloc[:i + 1]
            price = float(candles["close"].iloc[i])
            timestamp = candles.index[i]

            rec = self.strategy.evaluate(pair, window)

            # --- BUY logic ---
            if rec.signal == Signal.BUY and pair not in executor.positions:
                spend = min(max_position_usd, executor.cash)
                if spend >= 1.0:
                    order = executor.buy(pair, spend, price, reason=rec.reason)
                    if order.status == OrderStatus.FILLED:
                        open_trade = BacktestTrade(
                            pair=pair,
                            entry_time=timestamp,
                            entry_price=price,
                            quantity=order.quantity,
                            reason_entry=rec.reason,
                        )

            # --- SELL logic ---
            elif rec.signal == Signal.SELL and pair in executor.positions:
                pos = executor.positions[pair]
                order = executor.sell(pair, price, reason=rec.reason)
                if order.status == OrderStatus.FILLED and open_trade:
                    open_trade.exit_time = timestamp
                    open_trade.exit_price = price
                    open_trade.pnl = (price - open_trade.entry_price) * open_trade.quantity
                    open_trade.pnl_pct = ((price - open_trade.entry_price) / open_trade.entry_price) * 100
                    open_trade.reason_exit = rec.reason
                    trades.append(open_trade)
                    open_trade = None

            # --- Stop-loss / take-profit ---
            if pair in executor.positions:
                pos = executor.positions[pair]
                pnl_pct = pos.unrealized_pnl_pct(price)

                if pnl_pct <= -self.risk_cfg.stop_loss_pct:
                    order = executor.sell(pair, price, reason=f"Stop-loss at {pnl_pct:.1f}%")
                    if order.status == OrderStatus.FILLED and open_trade:
                        open_trade.exit_time = timestamp
                        open_trade.exit_price = price
                        open_trade.pnl = (price - open_trade.entry_price) * open_trade.quantity
                        open_trade.pnl_pct = pnl_pct
                        open_trade.reason_exit = f"Stop-loss at {pnl_pct:.1f}%"
                        trades.append(open_trade)
                        open_trade = None

                elif pnl_pct >= self.risk_cfg.take_profit_pct:
                    order = executor.sell(pair, price, reason=f"Take-profit at {pnl_pct:.1f}%")
                    if order.status == OrderStatus.FILLED and open_trade:
                        open_trade.exit_time = timestamp
                        open_trade.exit_price = price
                        open_trade.pnl = (price - open_trade.entry_price) * open_trade.quantity
                        open_trade.pnl_pct = pnl_pct
                        open_trade.reason_exit = f"Take-profit at {pnl_pct:.1f}%"
                        trades.append(open_trade)
                        open_trade = None

            # Track equity
            total = executor.total_value({pair: price})
            equity_curve.append(total)

        # Close any remaining open position at last price
        last_price = float(candles["close"].iloc[-1])
        if pair in executor.positions and open_trade:
            executor.sell(pair, last_price, reason="Backtest ended — closing position")
            open_trade.exit_time = candles.index[-1]
            open_trade.exit_price = last_price
            open_trade.pnl = (last_price - open_trade.entry_price) * open_trade.quantity
            open_trade.pnl_pct = ((last_price - open_trade.entry_price) / open_trade.entry_price) * 100
            open_trade.reason_exit = "Backtest ended"
            trades.append(open_trade)

        final_value = executor.total_value({pair: last_price})
        metrics = self._calculate_metrics(trades, equity_curve, final_value, candles)

        log.info(
            "backtest.complete",
            strategy=self.strategy.name,
            pair=pair,
            trades=len(trades),
            return_pct=metrics.total_return_pct,
            sharpe=metrics.sharpe_ratio,
            max_drawdown=metrics.max_drawdown_pct,
        )

        return BacktestResult(
            strategy_name=self.strategy.name,
            pair=pair,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            candles=candles,
        )

    def _calculate_metrics(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[float],
        final_value: float,
        candles: pd.DataFrame,
    ) -> PerformanceMetrics:
        """Calculate all performance metrics from trade results."""
        m = PerformanceMetrics()
        m.starting_balance = self.starting_balance
        m.ending_balance = round(final_value, 2)
        m.total_pnl = round(final_value - self.starting_balance, 2)
        m.total_return_pct = round(((final_value - self.starting_balance) / self.starting_balance) * 100, 2)
        m.total_trades = len(trades)
        m.start_date = str(candles.index[0])[:10]
        m.end_date = str(candles.index[-1])[:10]

        if not trades:
            return m

        # Win/loss breakdown
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        m.winning_trades = len(wins)
        m.losing_trades = len(losses)
        m.win_rate = round((len(wins) / len(trades)) * 100, 1)

        if wins:
            m.avg_win_pct = round(sum(t.pnl_pct for t in wins) / len(wins), 2)
        if losses:
            m.avg_loss_pct = round(sum(t.pnl_pct for t in losses) / len(losses), 2)

        all_pnl_pcts = [t.pnl_pct for t in trades]
        m.best_trade_pct = round(max(all_pnl_pcts), 2) if all_pnl_pcts else 0
        m.worst_trade_pct = round(min(all_pnl_pcts), 2) if all_pnl_pcts else 0

        # Profit factor
        total_gains = sum(t.pnl for t in wins) if wins else 0
        total_losses = abs(sum(t.pnl for t in losses)) if losses else 0
        m.profit_factor = round(total_gains / total_losses, 2) if total_losses > 0 else float("inf")

        # Sharpe ratio (annualized, assuming hourly candles)
        if len(equity_curve) > 1:
            returns = pd.Series(equity_curve).pct_change().dropna()
            if returns.std() > 0:
                periods_per_year = 365 * 24  # hourly candles
                m.sharpe_ratio = round(
                    (returns.mean() / returns.std()) * math.sqrt(periods_per_year), 2
                )

        # Max drawdown
        if equity_curve:
            peak = equity_curve[0]
            max_dd = 0.0
            for val in equity_curve:
                if val > peak:
                    peak = val
                dd = (peak - val) / peak * 100
                if dd > max_dd:
                    max_dd = dd
            m.max_drawdown_pct = round(max_dd, 2)

        # Average holding period
        holding_hours = []
        for t in trades:
            if t.entry_time and t.exit_time:
                delta = t.exit_time - t.entry_time
                holding_hours.append(delta.total_seconds() / 3600)
        if holding_hours:
            avg_h = sum(holding_hours) / len(holding_hours)
            if avg_h < 24:
                m.avg_holding_period = f"{avg_h:.1f} hours"
            else:
                m.avg_holding_period = f"{avg_h / 24:.1f} days"

        return m


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
@dataclass
class BacktestResult:
    strategy_name: str
    pair: str
    metrics: PerformanceMetrics
    trades: list[BacktestTrade]
    equity_curve: list[float]
    candles: pd.DataFrame

    def print_report(self) -> None:
        """Print a formatted performance report to the console."""
        m = self.metrics
        print("\n" + "=" * 60)
        print(f"  BACKTEST REPORT: {self.strategy_name.upper()} on {self.pair}")
        print("=" * 60)
        print(f"  Period:           {m.start_date} → {m.end_date}")
        print(f"  Starting Balance: ${m.starting_balance:,.2f}")
        print(f"  Ending Balance:   ${m.ending_balance:,.2f}")
        print(f"  Total Return:     {m.total_return_pct:+.2f}%  (${m.total_pnl:+,.2f})")
        print("-" * 60)
        print(f"  Total Trades:     {m.total_trades}")
        print(f"  Win Rate:         {m.win_rate}%  ({m.winning_trades}W / {m.losing_trades}L)")
        print(f"  Avg Win:          {m.avg_win_pct:+.2f}%")
        print(f"  Avg Loss:         {m.avg_loss_pct:+.2f}%")
        print(f"  Best Trade:       {m.best_trade_pct:+.2f}%")
        print(f"  Worst Trade:      {m.worst_trade_pct:+.2f}%")
        print(f"  Profit Factor:    {m.profit_factor}")
        print("-" * 60)
        print(f"  Sharpe Ratio:     {m.sharpe_ratio}")
        print(f"  Max Drawdown:     {m.max_drawdown_pct:.2f}%")
        print(f"  Avg Hold Time:    {m.avg_holding_period}")
        print("=" * 60)

        if self.trades:
            print("\n  Recent Trades:")
            for t in self.trades[-5:]:
                emoji = "✅" if t.pnl > 0 else "❌"
                print(
                    f"    {emoji} {str(t.entry_time)[:16]} → {str(t.exit_time)[:16]}"
                    f"  ${t.entry_price:,.2f} → ${t.exit_price:,.2f}"
                    f"  {t.pnl_pct:+.2f}%  (${t.pnl:+.2f})"
                )
        print()

    def to_json(self) -> dict[str, Any]:
        """Export results as a JSON-serializable dict (for the dashboard)."""
        return {
            "strategy": self.strategy_name,
            "pair": self.pair,
            "metrics": self.metrics.to_dict(),
            "equity_curve": [round(v, 2) for v in self.equity_curve],
            "trades": [
                {
                    "entry_time": str(t.entry_time)[:19],
                    "exit_time": str(t.exit_time)[:19] if t.exit_time else None,
                    "entry_price": round(t.entry_price, 2),
                    "exit_price": round(t.exit_price, 2) if t.exit_price else None,
                    "pnl": round(t.pnl, 2),
                    "pnl_pct": round(t.pnl_pct, 2),
                    "reason_entry": t.reason_entry,
                    "reason_exit": t.reason_exit,
                }
                for t in self.trades
            ],
        }
