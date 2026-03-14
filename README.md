# Crypto Trading Agent

An automated cryptocurrency trading agent that evaluates markets, executes strategies, and manages a portfolio — starting safely with paper trading before ever touching real funds.

> **⚠️ Disclaimer:** This is a personal learning and engineering project. Automated trading carries significant financial risk. Never trade with money you can't afford to lose. This software comes with no guarantees of profit. Consult a financial advisor before deploying real capital.

---

## Architecture Overview

The agent is built as a pipeline of independent, testable components. Each component has a single responsibility and communicates through well-defined interfaces.

```
┌─────────────────────────────────────────────────────┐
│                   Agent Scheduler                    │
│          (ticks every N seconds via APScheduler)     │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
       ▼              ▼              ▼
 ┌───────────┐  ┌───────────┐  ┌───────────────┐
 │  Market   │  │ Strategy  │  │   Portfolio    │
 │   Data    │  │  Engine   │  │   Manager      │
 │   Feed    │  │           │  │                │
 └─────┬─────┘  └─────┬─────┘  └──────┬────────┘
       │              │               │
       │         (evaluates)     (enforces risk
       │              │          limits, tracks
       ▼              ▼          positions)
  ┌─────────┐   ┌──────────┐        │
  │  ccxt   │   │ Indicators│       ▼
  │ Exchange│   │ (ta lib)  │  ┌──────────┐
  │   API   │   └──────────┘  │ Executor │
  └─────────┘                 │ (paper / │
                              │  live)   │
                              └──────────┘
```

### Component Responsibilities

| Component | Location | Purpose |
|---|---|---|
| **Config** | `src/agent/config.py` | Loads and validates all settings from YAML, env vars, and `.env` files using Pydantic. Single source of truth. |
| **Market Data Feed** | `src/market_data/` | Connects to exchanges via `ccxt`, fetches OHLCV candles and order book data. Will support both REST polling and WebSocket streaming. |
| **Strategy Engine** | `src/agent/strategies/` | Pluggable strategy system. Each strategy subclasses `BaseStrategy` and implements `evaluate()` → returns BUY / SELL / HOLD signals with confidence scores. |
| **Indicators** | `src/agent/indicators/` | Technical analysis helpers (RSI, MACD, Bollinger Bands, etc.) wrapping the `ta` library for easy use inside strategies. |
| **Portfolio Manager** | `src/portfolio/` | Tracks all open positions, calculates P&L, enforces risk limits (max position size, stop-loss, daily loss cap). |
| **Executor** | `src/execution/` | Translates trade signals into actual orders. `PaperExecutor` simulates fills locally; `LiveExecutor` submits real orders via ccxt. |
| **Scheduler** | Part of `main.py` | Uses APScheduler to call the strategy at a fixed interval, feeding it fresh candle data each tick. |
| **Logging** | `structlog` | Every decision, trade, and error is logged with structured context for easy debugging and audit trails. |

---

## Project Structure

```
crypto-trading-agent/
├── configs/
│   └── config.default.yaml     # Default settings (committed)
│   └── config.local.yaml       # Your overrides (git-ignored)
├── data/
│   ├── historical/             # Downloaded candle data for backtesting
│   └── cache/                  # Temporary data cache
├── logs/                       # Agent log files
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── config.py           # Pydantic config system
│   │   ├── main.py             # Entry point & component wiring
│   │   ├── strategies/
│   │   │   ├── __init__.py
│   │   │   └── base.py         # BaseStrategy ABC & Signal types
│   │   └── indicators/
│   │       └── __init__.py
│   ├── market_data/
│   │   └── __init__.py
│   ├── execution/
│   │   └── __init__.py
│   ├── portfolio/
│   │   └── __init__.py
│   └── utils/
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   └── test_config.py          # Config loading smoke tests
├── .env.example                # Template for API keys
├── .gitignore
├── pyproject.toml              # Dependencies & project metadata
└── README.md                   # ← You are here
```

---

## Quick Start

```bash
# 1. Clone and enter the project
cd crypto-trading-agent

# 2. Create a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Copy and configure your settings
cp .env.example .env
cp configs/config.default.yaml configs/config.local.yaml
# Edit .env with your exchange API keys
# Edit config.local.yaml with your preferences

# 5. Run the tests
pytest

# 6. Start the agent (paper mode by default)
trading-agent
```

---

## Configuration

Settings are layered in this priority order (highest wins):

1. `configs/config.default.yaml` — safe defaults shipped with the project
2. `configs/config.local.yaml` — your personal overrides (git-ignored)
3. Environment variables — prefixed `AGENT_` (e.g., `AGENT_MODE=live`)
4. `.env` file — loaded automatically via python-dotenv

All config values are validated at startup by Pydantic. If something is wrong, the agent will fail fast with a clear error message rather than silently misbehaving.

---

## Available Strategies

| Strategy | Config Name | Description |
|---|---|---|
| **SMA Crossover** | `sma_crossover` | Buys when fast SMA crosses above slow SMA. Classic trend-following. |
| **RSI** | `rsi` | Buys when RSI < 30 (oversold), sells when RSI > 70 (overbought). Mean-reversion. |
| **MACD** | `macd` | Buys on MACD/signal bullish crossover, sells on bearish crossover. Momentum. |
| **Bollinger Bands** | `bollinger_bands` | Buys when price breaks below lower band, sells above upper band. Volatility-based. |

To switch strategies, edit `configs/config.default.yaml` and change `strategy.name`.

---

## Backtesting

Run any strategy against historical data to see how it would have performed:

```bash
# Backtest default strategy (SMA Crossover) on BTC/USDT
python -m agent.run_backtest

# Backtest RSI strategy with 60 days of data
python -m agent.run_backtest --strategy rsi --days 60

# Compare ALL strategies side-by-side and save results
python -m agent.run_backtest --compare --save-json

# Open the visual dashboard in your browser
python -m agent.dashboard
```

The dashboard shows equity curves, trade history, win rates, Sharpe ratios, and more.

---

## Live Dashboard

Run the agent with a real-time web dashboard that updates every 5 seconds:

```bash
# Start agent + live dashboard
python -m agent.live

# Then open in your browser:
# http://localhost:5555
```

The dashboard has two modes:
- **Simple** — portfolio value, P&L, prices, and trade history (clean and focused)
- **Advanced** — adds equity curve, strategy signals, confidence scores, and detailed metrics

Toggle between them with the button in the top-right corner.

---

## Roadmap

### Phase 1 — Foundation ✅ (complete)
- [x] Project scaffolding & folder structure
- [x] Config system with validation
- [x] Base strategy interface
- [x] Market data feed (ccxt REST polling)
- [x] Paper trading executor
- [x] Portfolio manager with risk controls (stop-loss, take-profit, position limits)
- [x] First strategy: SMA Crossover
- [x] Agent loop with scheduler

### Phase 2 — Backtesting & Multi-Strategy ✅ (complete)
- [x] Backtesting engine (run strategies on historical data)
- [x] Performance metrics (Sharpe ratio, max drawdown, win rate, profit factor)
- [x] Multiple strategies: RSI, MACD, Bollinger Bands
- [x] Strategy comparison tool (--compare flag)
- [x] HTML dashboard with equity curves, trade history, metrics

### Phase 3 — Live Dashboard & Monitoring ✅ (complete)
- [x] Live web dashboard with real-time updates (Flask + polling)
- [x] Simple / Advanced mode toggle
- [x] Live price ticker, equity curve, signal log, trade history
- [x] Thread-safe state store bridging agent and dashboard

### Phase 4 — Live Trading (only after extensive paper testing)
- [ ] Live executor with exchange order submission
- [ ] Dry-run mode (submit & cancel immediately to verify flow)
- [ ] Position reconciliation with exchange
- [ ] Emergency stop button
- [ ] Cloud deployment for 24/7 operation
- [ ] Alerting (Telegram, Discord, email notifications)

---

## Safety Philosophy

1. **Paper first, always.** The default mode is `paper`. You have to explicitly change it to go live.
2. **Risk limits are mandatory.** Stop-losses, position caps, and daily loss limits are baked into the config and enforced by the portfolio manager.
3. **Every decision is logged.** Full audit trail of every signal, trade, and state change.
4. **Fail fast.** Invalid config, unreachable exchange, or unexpected data → the agent stops rather than guessing.
