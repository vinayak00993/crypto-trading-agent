"""
Backtest runner — run from the command line:

    python -m agent.run_backtest
    python -m agent.run_backtest --strategy rsi --pair BTC/USDT --days 60
    python -m agent.run_backtest --strategy macd --days 90 --balance 50000

Connects to Kraken, downloads historical candles, runs the strategy,
and prints a full performance report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog

from agent.config import load_config, PROJECT_ROOT
from agent.strategies.loader import load_strategy, STRATEGY_REGISTRY
from agent.backtest import Backtester
from market_data.feed import MarketDataFeed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a backtest on historical data")
    parser.add_argument("--strategy", type=str, default=None, help="Strategy name (default: from config)")
    parser.add_argument("--pair", type=str, default=None, help="Trading pair (default: first in config)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to test (default: 30)")
    parser.add_argument("--timeframe", type=str, default=None, help="Candle timeframe (default: from config)")
    parser.add_argument("--balance", type=float, default=None, help="Starting balance (default: from config)")
    parser.add_argument("--save-json", action="store_true", help="Save results to data/backtest_results.json")
    parser.add_argument("--compare", action="store_true", help="Compare all strategies")
    args = parser.parse_args()

    cfg = load_config()

    # Setup logging
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler(sys.stdout)])
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    log = structlog.get_logger()

    # Connect to exchange
    feed = MarketDataFeed(cfg.exchange, cfg.trading)
    feed.connect()

    pair = args.pair or cfg.trading.pairs[0]
    timeframe = args.timeframe or cfg.trading.default_timeframe
    balance = args.balance or cfg.paper.starting_balance

    # Calculate how many candles we need
    timeframe_hours = {"1m": 1/60, "5m": 5/60, "15m": 0.25, "1h": 1, "4h": 4, "1d": 24}
    hours_per_candle = timeframe_hours.get(timeframe, 1)
    candles_needed = min(int((args.days * 24) / hours_per_candle), 720)  # most exchanges cap at 720

    log.info("backtest.fetching_data", pair=pair, timeframe=timeframe, candles=candles_needed)
    candles = feed.fetch_candles(pair, timeframe=timeframe, limit=candles_needed)

    if candles.empty or len(candles) < 50:
        print(f"\n❌ Not enough candle data: got {len(candles)}, need at least 50.")
        print("   Try a shorter timeframe (e.g. --timeframe 1h) or fewer days.")
        sys.exit(1)

    print(f"\n📊 Loaded {len(candles)} candles for {pair} ({timeframe}) from {str(candles.index[0])[:10]} to {str(candles.index[-1])[:10]}")

    if args.compare:
        # Run all strategies and compare
        print("\n🔄 Comparing all strategies...\n")
        results = []
        for name in STRATEGY_REGISTRY:
            strat = load_strategy(name, cfg.strategy.params)
            bt = Backtester(strat, starting_balance=balance, risk_cfg=cfg.risk)
            result = bt.run(pair, candles)
            result.print_report()
            results.append(result)

        # Print comparison table
        print("\n" + "=" * 80)
        print("  STRATEGY COMPARISON")
        print("=" * 80)
        print(f"  {'Strategy':<20} {'Return':>10} {'Trades':>8} {'Win Rate':>10} {'Sharpe':>8} {'Max DD':>10}")
        print("-" * 80)
        for r in sorted(results, key=lambda x: x.metrics.total_return_pct, reverse=True):
            m = r.metrics
            print(
                f"  {r.strategy_name:<20} {m.total_return_pct:>+9.2f}% {m.total_trades:>8} "
                f"{m.win_rate:>9.1f}% {m.sharpe_ratio:>8.2f} {m.max_drawdown_pct:>9.2f}%"
            )
        print("=" * 80 + "\n")

        if args.save_json:
            _save_results([r.to_json() for r in results])

    else:
        # Run single strategy
        strategy_name = args.strategy or cfg.strategy.name
        strategy = load_strategy(strategy_name, cfg.strategy.params)

        bt = Backtester(strategy, starting_balance=balance, risk_cfg=cfg.risk)
        result = bt.run(pair, candles)
        result.print_report()

        if args.save_json:
            _save_results([result.to_json()])


def _save_results(data: list[dict]) -> None:
    out_path = PROJECT_ROOT / "data" / "backtest_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"💾 Results saved to {out_path}")


if __name__ == "__main__":
    main()
