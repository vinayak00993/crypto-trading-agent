"""
Monthly Backtest Runner — downloads 5-minute candles in chunks and
backtests each 30-day window separately per strategy.

Usage:
    python -m agent.monthly_backtest
    python -m agent.monthly_backtest --pair BTC/USDT --months 6
    python -m agent.monthly_backtest --pair ETH/USDT --months 3

This gives you an accurate picture of how each strategy would have
traded on the same 5-minute timeframe your live agent uses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt
import pandas as pd
import structlog

from agent.config import load_config, PROJECT_ROOT
from agent.strategies.loader import load_strategy, STRATEGY_REGISTRY
from agent.backtest import Backtester, BacktestResult

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
def setup_logging() -> None:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler(sys.stdout)])
    structlog.configure(
        processors=[structlog.stdlib.add_log_level, structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


# ---------------------------------------------------------------------------
# Data downloader — fetches 5m candles in chunks
# ---------------------------------------------------------------------------
def download_candles(
    exchange_name: str,
    pair: str,
    timeframe: str,
    days: int,
    rate_limit_ms: int = 1200,
) -> pd.DataFrame:
    """
    Download historical candles by stepping backwards in time.

    Most exchanges return max 720 candles per request.
    For 5m candles, 720 candles = 2.5 days.
    For 180 days, we need ~72 requests.
    """
    exchange_class = getattr(ccxt, exchange_name)
    exchange = exchange_class({"enableRateLimit": True, "rateLimit": rate_limit_ms})
    exchange.load_markets()

    # Calculate time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    timeframe_ms = {
        "1m": 60_000, "5m": 300_000, "15m": 900_000,
        "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
    }
    tf_ms = timeframe_ms.get(timeframe, 300_000)
    chunk_size = 720
    chunk_duration_ms = chunk_size * tf_ms

    all_candles = []
    current_start = int(start_time.timestamp() * 1000)
    target_end = int(end_time.timestamp() * 1000)
    total_chunks = max(1, (target_end - current_start) // chunk_duration_ms + 1)

    print(f"\n  Downloading {pair} {timeframe} candles for {days} days...")
    print(f"  Date range: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}")
    print(f"  Estimated chunks: {total_chunks}\n")

    chunk_num = 0
    while current_start < target_end:
        chunk_num += 1
        progress = min(100, int((chunk_num / total_chunks) * 100))
        sys.stdout.write(f"\r  Downloading... {progress}% ({chunk_num}/{total_chunks} chunks)")
        sys.stdout.flush()

        try:
            raw = exchange.fetch_ohlcv(
                pair,
                timeframe=timeframe,
                since=current_start,
                limit=chunk_size,
            )
        except Exception as e:
            print(f"\n  Warning: chunk {chunk_num} failed ({e}), retrying...")
            time.sleep(2)
            try:
                raw = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=current_start, limit=chunk_size)
            except Exception:
                print(f"  Skipping chunk {chunk_num}")
                current_start += chunk_duration_ms
                continue

        if not raw:
            break

        all_candles.extend(raw)

        # Move forward to after the last candle we received
        last_ts = raw[-1][0]
        current_start = last_ts + tf_ms

        # Respect rate limits
        time.sleep(rate_limit_ms / 1000 + 0.1)

    print(f"\r  Downloaded {len(all_candles)} candles across {chunk_num} chunks.     \n")

    if not all_candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    # Build DataFrame and deduplicate
    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp")
    df.set_index("timestamp", inplace=True)

    return df


# ---------------------------------------------------------------------------
# Split data into monthly windows
# ---------------------------------------------------------------------------
def split_by_month(candles: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """Split candle data into 30-day windows, labeled by month."""
    windows = []
    if candles.empty:
        return windows

    start = candles.index[0]
    end = candles.index[-1]

    current = start
    while current < end:
        window_end = current + timedelta(days=30)
        mask = (candles.index >= current) & (candles.index < window_end)
        window = candles.loc[mask]

        if len(window) >= 50:  # minimum candles needed
            label = current.strftime("%b %Y")
            windows.append((label, window))

        current = window_end

    return windows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Monthly backtest with 5-minute candles")
    parser.add_argument("--pair", type=str, default=None, help="Trading pair (default: first in config)")
    parser.add_argument("--months", type=int, default=6, help="Months of history (default: 6)")
    parser.add_argument("--timeframe", type=str, default="5m", help="Candle timeframe (default: 5m)")
    parser.add_argument("--balance", type=float, default=2500, help="Starting balance per strategy (default: 2500)")
    parser.add_argument("--save", action="store_true", help="Save results to JSON")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config()

    pair = args.pair or cfg.trading.pairs[0]
    days = args.months * 30

    # Download full history
    candles = download_candles(
        exchange_name=cfg.exchange.name,
        pair=pair,
        timeframe=args.timeframe,
        days=days,
        rate_limit_ms=cfg.exchange.rate_limit_ms,
    )

    if candles.empty or len(candles) < 100:
        print(f"\n  Not enough data: got {len(candles)} candles. Try fewer months or a longer timeframe.")
        sys.exit(1)

    print(f"  Total: {len(candles)} candles from {str(candles.index[0])[:10]} to {str(candles.index[-1])[:10]}")

    # Split into monthly windows
    windows = split_by_month(candles)
    print(f"  Split into {len(windows)} monthly windows\n")

    # Get strategy names (exclude consensus)
    strategy_names = [s for s in STRATEGY_REGISTRY if s != "consensus"]

    # Run backtests
    # Structure: {strategy: {month: BacktestResult}}
    all_results: dict[str, dict[str, BacktestResult]] = {s: {} for s in strategy_names}
    full_results: dict[str, BacktestResult] = {}

    # Full period backtest per strategy
    print("=" * 80)
    print(f"  FULL PERIOD BACKTEST: {str(candles.index[0])[:10]} to {str(candles.index[-1])[:10]}")
    print("=" * 80)

    for name in strategy_names:
        strategy = load_strategy(name, cfg.strategy.params)
        bt = Backtester(strategy, starting_balance=args.balance, risk_cfg=cfg.risk)
        result = bt.run(pair, candles)
        full_results[name] = result

    # Print full period comparison
    print(f"\n  {'Strategy':<20} {'Return':>10} {'Trades':>8} {'Win Rate':>10} {'Sharpe':>8} {'Max DD':>10}")
    print("-" * 70)
    for name in sorted(strategy_names, key=lambda n: full_results[n].metrics.total_return_pct, reverse=True):
        m = full_results[name].metrics
        print(f"  {name:<20} {m.total_return_pct:>+9.2f}% {m.total_trades:>8} {m.win_rate:>9.1f}% {m.sharpe_ratio:>8.2f} {m.max_drawdown_pct:>9.2f}%")

    # Monthly backtests
    print("\n\n" + "=" * 80)
    print("  MONTHLY BREAKDOWN")
    print("=" * 80)

    monthly_summary: list[dict] = []

    for month_label, window in windows:
        print(f"\n  --- {month_label} ({len(window)} candles, {str(window.index[0])[:10]} to {str(window.index[-1])[:10]}) ---")
        print(f"  {'Strategy':<20} {'Return':>10} {'Trades':>8} {'Win Rate':>10} {'Best Trade':>12} {'Worst Trade':>12}")
        print("  " + "-" * 75)

        month_data = {"month": month_label, "start": str(window.index[0])[:10], "end": str(window.index[-1])[:10]}
        month_winner = None
        month_best_return = -999

        for name in strategy_names:
            strategy = load_strategy(name, cfg.strategy.params)
            bt = Backtester(strategy, starting_balance=args.balance, risk_cfg=cfg.risk)
            result = bt.run(pair, window)
            all_results[name][month_label] = result

            m = result.metrics
            winner_tag = ""
            if m.total_return_pct > month_best_return:
                month_best_return = m.total_return_pct
                month_winner = name

            print(
                f"  {name:<20} {m.total_return_pct:>+9.2f}% {m.total_trades:>8} "
                f"{m.win_rate:>9.1f}% {m.best_trade_pct:>+11.2f}% {m.worst_trade_pct:>+11.2f}%"
            )

            month_data[name] = {
                "return_pct": m.total_return_pct,
                "trades": m.total_trades,
                "win_rate": m.win_rate,
                "sharpe": m.sharpe_ratio,
                "max_drawdown": m.max_drawdown_pct,
            }

        month_data["winner"] = month_winner
        monthly_summary.append(month_data)
        if month_winner:
            print(f"  >>> Winner: {month_winner} ({month_best_return:+.2f}%)")

    # Strategy win count
    print("\n\n" + "=" * 80)
    print("  STRATEGY SCORECARD — Who Won Each Month?")
    print("=" * 80)

    win_counts: dict[str, int] = {s: 0 for s in strategy_names}
    for month in monthly_summary:
        winner = month.get("winner", "")
        if winner:
            win_counts[winner] = win_counts.get(winner, 0) + 1

    for name in sorted(win_counts, key=lambda n: win_counts[n], reverse=True):
        months_won = [m["month"] for m in monthly_summary if m.get("winner") == name]
        bar = "#" * win_counts[name]
        print(f"  {name:<20} {win_counts[name]} wins  {bar}  ({', '.join(months_won)})")

    # Overall recommendation
    print("\n" + "=" * 80)
    best_overall = max(strategy_names, key=lambda n: full_results[n].metrics.total_return_pct)
    most_wins = max(strategy_names, key=lambda n: win_counts[n])
    most_consistent = min(strategy_names, key=lambda n: full_results[n].metrics.max_drawdown_pct)

    print(f"  Best overall return:    {best_overall} ({full_results[best_overall].metrics.total_return_pct:+.2f}%)")
    print(f"  Most months won:        {most_wins} ({win_counts[most_wins]} months)")
    print(f"  Lowest max drawdown:    {most_consistent} ({full_results[most_consistent].metrics.max_drawdown_pct:.2f}%)")
    print("=" * 80 + "\n")

    # Save results
    if args.save:
        output = {
            "pair": pair,
            "timeframe": args.timeframe,
            "total_candles": len(candles),
            "date_range": f"{str(candles.index[0])[:10]} to {str(candles.index[-1])[:10]}",
            "full_period": {name: full_results[name].to_json() for name in strategy_names},
            "monthly": monthly_summary,
        }
        out_path = PROJECT_ROOT / "data" / "monthly_backtest.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"  Results saved to {out_path}\n")


if __name__ == "__main__":
    main()
