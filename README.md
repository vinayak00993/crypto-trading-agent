# Crypto Trading Agent

An autonomous multi-strategy crypto trading agent with an ML meta-learner that gets smarter over time.

## What This Is

A paper trading system that runs 9 independent strategy "pods" across 3 cryptocurrencies (BTC, ETH, SOL), competing head-to-head. A 9th ML meta-learner pod observes all 8, learns which signal combinations actually predict profitable trades, and makes its own autonomous trades based on a gradient boosting model.

**Live Dashboard:** https://crypto-trading-agent-production.up.railway.app

## Architecture

```
$22,500 total paper money ($2,500 per pod)

TECHNICAL STRATEGIES ($2,500 each)
  SMA Crossover    - Trend following (fast/slow moving average cross)
  RSI              - Momentum (buy oversold <35, sell overbought >65)
  MACD             - Momentum (bullish/bearish crossovers)
  Bollinger Bands  - Volatility (buy lower band break, sell upper)

FUNDAMENTAL STRATEGIES ($2,500 each)
  Fear & Greed     - Contrarian (buy extreme fear <20, sell extreme greed >75)
  Network Activity - On-chain (BTC active addresses, tx count, compute power)
  Volume Momentum  - Volume spikes confirming price direction
  DCA Baseline     - Dollar cost averaging benchmark (buy every N ticks)

ML META-LEARNER ($2,500) - AUTONOMOUS
  Gradient boosting model that learns from all 8 pods
  - Observes every signal from every pod
  - Evaluates signal accuracy after 20 ticks
  - Trains ML model after 200+ samples
  - Learns signal COMBINATIONS (not just individual accuracy)
  - Incorporates external data (Fear and Greed, funding rates, BTC dominance)
  - Retrains every 50 new samples
  - Persistent memory - survives restarts (saved to data/ml_learner/)
```

## Trading Pairs
- BTC/USDT (Bitcoin)
- ETH/USDT (Ethereum)
- SOL/USDT (Solana)

## External Data Feeds (all free, no API keys)
- **Fear and Greed Index** - alternative.me API (market sentiment 0-100)
- **Blockchain stats** - blockchain.com API (active addresses, tx count, compute power)
- **BTC dominance** - alternative.me API (altcoin rotation signal)
- **Funding rates** - CoinGlass API (leveraged trader positioning)

## Project Structure

```
crypto-trading-agent/
  src/
    agent/
      config.py              - Pydantic config, layered YAML+env
      main.py                - Entry point (python -m agent.main)
      live.py                - Agent + dashboard (python -m agent.live)
      loop.py                - Main trading loop, 9 pods, ML signal feeding
      state.py               - Thread-safe StateStore singleton
      server.py              - Flask web server + dashboard HTML
      backtest.py            - Backtesting engine
      run_backtest.py        - CLI: python -m agent.run_backtest
      monthly_backtest.py    - Downloads 5m candles, monthly comparison
      dashboard.py           - Static backtest dashboard generator
      strategies/
        base.py              - BaseStrategy ABC, Signal enum, TradeRecommendation
        sma_crossover.py     - Simple Moving Average crossover
        rsi.py               - Relative Strength Index
        macd.py              - Moving Average Convergence Divergence
        bollinger_bands.py   - Bollinger Bands volatility
        consensus.py         - Meta-strategy (not used in multi-pod mode)
        fear_greed.py        - Fear and Greed contrarian
        network_activity.py  - BTC on-chain metrics
        volume_momentum.py   - Volume spike confirmation
        dca_baseline.py      - Dollar cost averaging benchmark
        ml_meta_learner.py   - ML v2: persistent, gradient boosting, external data
        loader.py            - STRATEGY_REGISTRY + group labels
    market_data/feed.py      - ccxt MarketDataFeed (Kraken)
    execution/paper.py       - PaperExecutor, Order, Position
    portfolio/manager.py     - PortfolioManager, risk controls
    utils/
  tests/                     - Unit tests
  configs/config.default.yaml - All configuration
  data/
    ml_learner/              - Persistent ML state (gitignored)
      training_samples.json  - All training data
      pod_stats.json         - Pod accuracy scores
      model_meta.json        - Model metadata
  Dockerfile                 - Cloud deployment (Railway)
  pyproject.toml             - Dependencies (incl. scikit-learn)
```

## Configuration (configs/config.default.yaml)

Key settings:
- Exchange: Kraken (Binance geo-blocked for user)
- Pairs: BTC/USDT, ETH/USDT, SOL/USDT
- Timeframe: 5-minute candles
- Tick interval: 30 seconds
- Starting balance: $22,500 ($2,500 x 9 pods)
- Risk: 40% max position per pod, 2% stop loss, 3% take profit

## ML Meta-Learner Details

### Learning Phases
1. LEARNING (0-200 samples): Observes pods, uses weighted voting fallback
2. WARMING (200-500 samples): ML model active but conservative
3. AUTONOMOUS (500+ samples): Full ML model, confident trading

### Features the ML Model Sees
- 8 pod signals (BUY=1, HOLD=0, SELL=-1)
- 8 pod confidence scores
- 8 pod rolling accuracy scores
- Fear and Greed Index (normalized)
- BTC funding rate
- BTC dominance (normalized)
- BTC 24h price change
- Recent price momentum

### Persistent Memory
All learning data saves to data/ml_learner/ every 25 ticks.
On Railway, this is mounted to a persistent volume at /app/data.
Agent restarts load all previous knowledge instantly.

## Commands

### Run locally (Cursor terminal)
```
cd crypto-trading-agent
.venv\Scripts\Activate.ps1
python -m agent.live
```
Dashboard at http://localhost:5555

### Run backtests
```
python -m agent.run_backtest --compare --save-json --days 30
python -m agent.monthly_backtest --pair BTC/USDT --months 6 --save
```

### Push to cloud (PowerShell)
```
cd "$HOME\OneDrive\Desktop\trading agent files\crypto-trading-agent"
git add .
git commit -m "description"
git push
```
Railway auto-deploys from GitHub.

## Cloud Deployment (Railway)
- URL: https://crypto-trading-agent-production.up.railway.app
- Plan: Hobby ($5/month)
- Persistent volume: /app/data for ML learner state
- Auto-deploy: Pushes to main branch trigger redeploy

## What is Left to Build

### Phase 5: Live Trading
- Connect funded Kraken API key
- Swap PaperExecutor for real executor
- Add trading fees (0.26% per trade)
- Add slippage protection
- Start with $50-100 per pod
- Add kill switch (max loss threshold)
- Add Telegram/Discord alerts

### Phase 6: Advanced
- Additional data feeds (Google Trends, S&P 500 correlation, liquidation data)
- More sophisticated ML (LSTM, transformer models)
- Prediction market agent (separate project)
- Scale to 10-15 autonomous agents

## Research Notes
- MACD outperformed other strategies on BTC backtests (+1.28% over 30 days)
- RSI won live with +0.24% on Railways 4-pod run
- Fear and Greed at extreme fear (<20) is historically one of the most reliable buy signals
- Equal pod weighting is evidence-backed (Bates and Granger 1969, forecast combination puzzle)
- Crypto markets are less efficient than stocks, making technical analysis more effective
- Academic research supports combining strategies over individual ones

## Known Issues
- Local Windows: Unicode arrow character in ML log messages causes encoding error (cosmetic only, does not affect Railway)
- Local Windows: numpy bool JSON serialization error on save_state (fix: cast to Python bool)
- Kraken does not have APT/USDT - removed from config
- Kraken API limits 5m candle history to ~720 candles (~2.5 days) - use 1h for longer backtests
