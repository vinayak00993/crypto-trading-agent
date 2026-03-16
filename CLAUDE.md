# Crypto Trading Agent — Claude Code Context

## User Profile
- **Name**: Vinayak Rao
- **GitHub**: github.com/vinayak00993
- **Setup**: Windows 11, PowerShell, GitHub Desktop
- **Skill level**: Not a native coder. Always give simple, step-by-step instructions with no assumed knowledge.
- **Project path**: `~\OneDrive\Desktop\trading agent files\crypto-trading-agent`

## Important Rules for Working with Vinayak
1. Never use zip files for code delivery
2. Number every step
3. Always combine git commands into one line with semicolons
4. Never refer to "the command from earlier" — always repeat commands in full
5. Keep instructions under 5 steps when possible
6. Always specify whether a command runs in PowerShell or browser
7. Never use PowerShell to edit Python files — it mangles whitespace
8. Each code block should contain only one thing

## Deployment
- **Railway URL**: https://crypto-trading-agent-production.up.railway.app
- **Railway plan**: Hobby ($5/month), asia-southeast1 region
- **Persistent volume**: mounted at /app/data (stores ML training data)
- **Port**: 8080 (Flask dashboard)
- **Entry point**: `python -m agent.live`
- **Auto-deploy**: pushes to main branch trigger Railway redeploy

## Architecture
$22,500 total paper capital ($2,500 per pod), 9 independent strategy pods:

### Technical Pods (price/chart-based)
- sma_crossover — Simple Moving Average crossover (fast=5, slow=15)
- rsi — Relative Strength Index (buy <30, sell >70)
- macd — MACD crossover (fast=12, slow=26, signal=9)
- bollinger_bands — Bollinger Bands (period=15, std=2.0)

### Fundamental Pods (external data)
- fear_greed — Contrarian Fear and Greed (buy <20, sell >75, recovery sell >45)
- network_activity — BTC on-chain metrics (active addresses, tx count, difficulty)
- volume_momentum — Volume-price divergence
- dca_baseline — Dollar Cost Averaging benchmark (buy every 20 ticks)

### ML Pod
- ml_meta_learner — Gradient boosting that learns from all other pods + external data

## Key Files
- src/agent/loop.py — Multi-pod orchestrator, runs all 9 pods simultaneously
- src/agent/server.py — Flask dashboard on port 8080
- src/agent/live.py — Entry point (python -m agent.live)
- src/agent/strategies/base.py — BaseStrategy, Signal, TradeRecommendation
- src/agent/strategies/loader.py — Strategy registry
- src/agent/strategies/fear_greed.py — v2: recovery sell + position tracking
- src/agent/strategies/network_activity.py — Uses "difficulty" not the banned words
- src/agent/strategies/external_feeds.py — All external data fetchers (v3)
- src/agent/strategies/ml_meta_learner.py — v2.1: atomic writes, overfit protection
- configs/config.default.yaml — Exchange: Kraken, pairs: BTC/USDT ETH/USDT SOL/USDT

## External Data Feeds (all free, no API key needed)
All in src/agent/strategies/external_feeds.py:
- Fear and Greed Index — alternative.me (sentiment 0-100)
- BTC Funding Rate — Binance Futures fapi
- BTC Open Interest — Binance Futures fapi
- Long/Short Ratio — Binance Futures
- Taker Buy/Sell Ratio — Binance Futures
- BTC Dominance — alternative.me
- Global Crypto Market — CoinGecko
- S&P 500 — Yahoo Finance (SPY)
- Google Trends — trendspyg ("bitcoin", "crypto crash", "buy crypto")
- BTC Network Activity — blockchain.com (active addresses, tx count, difficulty)

## ML Meta-Learner Details

### Phases
- LEARNING (0-200 clean samples): Weighted voting fallback
- WARMING (200-500): Would use ML but overfit guard blocks if accuracy >85%
- AUTONOMOUS (500+): Full gradient boosting model

### Current Status (March 15, 2026)
- 522 total samples, ~55 match current feature vector length
- Collecting fresh samples with expanded feature set (~38 features)
- Needs ~4-5 hours of running to reach 500 clean samples

### Training Parameters
- learning_rate=0.05, min_samples_leaf=20, subsample=0.7, max_features=0.8
- 70/30 train/test split
- Rejects model if accuracy >85% with <500 samples
- Retrains every 50 ticks, saves state every 25 ticks
- Atomic writes: .tmp then rename (crash-safe)

### Feature Vector
Per pod (8 pods): signal, confidence, accuracy = 24 features
External: fear_greed, funding_rate, btc_dominance, btc_24h_change, btc_open_interest, long_short_ratio, long_account_pct, taker_buy_sell_ratio, market_cap_change, sp500_change, trends_bitcoin, trends_crash, trends_buy, price_momentum = 14 features

## Risk Configuration
- 40% max position per pod, 2% stop-loss, 3% take-profit, max 2 open positions per pod

## Bugs Fixed (DO NOT reintroduce)
1. Railway bans the phrase for mining computational measurement — use "compute power" or "difficulty"
2. Fear and Greed pod tracks _bought_pairs, recovery sell at F&G >45
3. ML uses atomic writes (.tmp, .bak, rename) for crash safety
4. ML rejects overfit models (>85% accuracy with <500 samples)
5. ML filters mismatched feature vector lengths before training
6. Never edit .py via PowerShell — use Python or editor
7. .venv was removed from git — dont re-add

## Pending Features
1. **NEXT: Live trading** — Connect real Kraken API, start with $10-20 on BTC/SOL
2. Better dashboard — Per-pod P&L charts, equity curves
3. Telegram/Discord alerts

## Kraken Live Trading Research
- REST API uses legacy /0/ endpoints, ccxt handles auth
- HMAC-SHA512 auth, nonce must always increase
- Invalid nonce error if same key used by multiple instances
- Market orders require trading_agreement: agree
- No spot sandbox — real money from first order
- Fees: 0.16% maker / 0.26% taker
- Minimums: BTC=0.0001 (~$8-10), ETH=0.01 (~$25-35), SOL=0.01-0.05 (~$2-10)
- ETH minimums too large for small accounts — focus BTC and SOL
- Need Intermediate verification (full KYC) for API trading
- Plan: paper validation, shadow trading, micro-live ($10-20), scale to target
- Kill switches: exchange-side cancelallordersafter, app-side circuit breaker, SIGTERM handler
- Persist circuit breaker state to disk
- Use limit orders (saves 0.10% per side)

## Git Push Command (always this format)
```powershell
cd "$HOME\OneDrive\Desktop\trading agent files\crypto-trading-agent"; git add .; git commit -m "description"; git push
```
