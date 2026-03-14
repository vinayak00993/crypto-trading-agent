"""
Live Dashboard Server — serves a real-time web dashboard for the trading agent.

Runs a lightweight Flask web server in a background thread.
The agent loop writes state → the server reads it → the browser polls for updates.

Usage:
    python -m agent.live        # starts agent + live dashboard
    Then open http://localhost:5555 in your browser
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from flask import Flask, Response

from agent.state import store

app = Flask(__name__)


@app.route("/")
def index() -> str:
    """Serve the live dashboard HTML."""
    return DASHBOARD_HTML


@app.route("/api/state")
def api_state() -> Response:
    """Return the current agent state as JSON."""
    state = store.snapshot()
    return Response(
        json.dumps(state, default=str),
        mimetype="application/json",
    )


def start_server(port: int = 5555) -> None:
    """Start the Flask server in a daemon thread."""
    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()


# ---------------------------------------------------------------------------
# The complete live dashboard HTML — self-contained, no external files needed
# ---------------------------------------------------------------------------
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto Trading Agent - Live Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0a0e14;
    color: #e1e4e8;
    min-height: 100vh;
  }

  /* --- Header --- */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 28px;
    border-bottom: 1px solid #1c2128;
    background: #0d1117;
  }
  .header-left { display: flex; align-items: center; gap: 16px; }
  .logo {
    font-size: 22px; font-weight: 700;
    background: linear-gradient(135deg, #58a6ff, #bc8cff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .status-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;
  }
  .status-running { background: rgba(63,185,80,0.15); color: #3fb950; }
  .status-stopped { background: rgba(248,81,73,0.15); color: #f85149; }
  .status-starting { background: rgba(210,153,34,0.15); color: #d29922; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; animation: pulse 2s infinite; }
  .status-running .status-dot { background: #3fb950; }
  .status-stopped .status-dot { background: #f85149; }
  .status-starting .status-dot { background: #d29922; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

  .header-right { display: flex; align-items: center; gap: 16px; }
  .meta-text { font-size: 12px; color: #8b949e; }

  /* --- Mode Toggle --- */
  .toggle-container {
    display: flex; background: #161b22; border-radius: 8px;
    border: 1px solid #30363d; overflow: hidden;
  }
  .toggle-btn {
    padding: 6px 16px; font-size: 12px; font-weight: 600;
    cursor: pointer; border: none; background: transparent; color: #8b949e;
    transition: all 0.2s;
  }
  .toggle-btn.active { background: #58a6ff; color: #0a0e14; }
  .toggle-btn:hover:not(.active) { color: #c9d1d9; }

  /* --- Main Layout --- */
  .container { padding: 24px 28px; max-width: 1400px; margin: 0 auto; }

  /* --- Cards Grid --- */
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px; }
  .card {
    background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 18px;
  }
  .card-label { font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
  .card-value { font-size: 26px; font-weight: 700; margin-top: 4px; }
  .card-sub { font-size: 11px; color: #8b949e; margin-top: 4px; }
  .positive { color: #3fb950; }
  .negative { color: #f85149; }
  .neutral { color: #58a6ff; }

  /* --- Sections --- */
  .section {
    background: #161b22; border: 1px solid #30363d; border-radius: 12px;
    padding: 20px; margin-bottom: 20px;
  }
  .section-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #c9d1d9; }

  /* --- Table --- */
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th {
    text-align: left; padding: 8px 10px; border-bottom: 2px solid #30363d;
    color: #8b949e; font-weight: 600; font-size: 11px; text-transform: uppercase;
  }
  td { padding: 8px 10px; border-bottom: 1px solid #21262d; }
  tr:hover { background: #1c2128; }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 6px;
    font-size: 11px; font-weight: 600;
  }
  .badge-buy { background: rgba(63,185,80,0.15); color: #3fb950; }
  .badge-sell { background: rgba(248,81,73,0.15); color: #f85149; }
  .badge-hold { background: rgba(139,148,158,0.15); color: #8b949e; }

  /* --- Chart --- */
  canvas { max-height: 300px; }

  /* --- Price Ticker --- */
  .ticker { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
  .ticker-item {
    display: flex; align-items: center; gap: 10px;
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 12px 18px; flex: 1; min-width: 200px;
  }
  .ticker-pair { font-weight: 600; font-size: 14px; }
  .ticker-price { font-size: 22px; font-weight: 700; }

  /* --- Responsive --- */
  @media (max-width: 768px) {
    .cards { grid-template-columns: repeat(2, 1fr); }
    .header { flex-direction: column; gap: 12px; }
  }

  /* --- Hidden in simple mode --- */
  .advanced-only { display: block; }
  body.simple-mode .advanced-only { display: none; }

  /* --- Refresh indicator --- */
  .refresh-bar {
    height: 2px; background: linear-gradient(90deg, transparent, #58a6ff, transparent);
    position: fixed; top: 0; left: 0; width: 100%;
    opacity: 0; transition: opacity 0.3s;
  }
  .refresh-bar.active { opacity: 1; animation: slide 1s linear; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(100%); } }
</style>
</head>
<body>
<div class="refresh-bar" id="refreshBar"></div>

<!-- Header -->
<div class="header">
  <div class="header-left">
    <span class="logo">Crypto Trading Agent</span>
    <span class="status-badge status-starting" id="statusBadge">
      <span class="status-dot"></span>
      <span id="statusText">Connecting...</span>
    </span>
  </div>
  <div class="header-right">
    <span class="meta-text" id="metaInfo">--</span>
    <div class="toggle-container">
      <button class="toggle-btn active" id="btnSimple" onclick="setMode('simple')">Simple</button>
      <button class="toggle-btn" id="btnAdvanced" onclick="setMode('advanced')">Advanced</button>
    </div>
  </div>
</div>

<div class="container">
  <!-- Price Ticker -->
  <div class="ticker" id="ticker"></div>

  <!-- Portfolio Cards -->
  <div class="cards" id="portfolioCards"></div>

  <!-- Equity Chart (advanced) -->
  <div class="section advanced-only" id="equitySection">
    <div class="section-title">Portfolio Value Over Time</div>
    <canvas id="equityChart"></canvas>
  </div>

  <!-- Open Positions -->
  <div class="section" id="positionsSection" style="display:none">
    <div class="section-title">Open Positions</div>
    <table><thead><tr>
      <th>Pair</th><th>Quantity</th><th>Entry Price</th><th>Current Price</th><th>P&L</th>
    </tr></thead><tbody id="positionsBody"></tbody></table>
  </div>

  <!-- Recent Signals (advanced) -->
  <div class="section advanced-only" id="signalsSection">
    <div class="section-title">Recent Strategy Signals</div>
    <table><thead><tr>
      <th>Time</th><th>Pair</th><th>Signal</th><th>Confidence</th><th>Reason</th>
    </tr></thead><tbody id="signalsBody"></tbody></table>
  </div>

  <!-- Trade Log -->
  <div class="section" id="tradesSection">
    <div class="section-title">Trade History</div>
    <table><thead><tr>
      <th>Time</th><th>Pair</th><th>Side</th><th>Price</th><th>Cost</th><th>Reason</th>
    </tr></thead><tbody id="tradesBody"></tbody></table>
  </div>
</div>

<script>
let equityChart = null;
let currentMode = 'simple';
let lastState = null;

// --- Mode Toggle ---
function setMode(mode) {
  currentMode = mode;
  document.body.classList.toggle('simple-mode', mode === 'simple');
  document.getElementById('btnSimple').classList.toggle('active', mode === 'simple');
  document.getElementById('btnAdvanced').classList.toggle('active', mode === 'advanced');
  localStorage.setItem('dashboardMode', mode);
}

// --- Data Fetch ---
async function fetchState() {
  try {
    document.getElementById('refreshBar').classList.add('active');
    const resp = await fetch('/api/state');
    const state = await resp.json();
    lastState = state;
    updateUI(state);
    setTimeout(() => document.getElementById('refreshBar').classList.remove('active'), 500);
  } catch (e) {
    console.error('Fetch failed:', e);
  }
}

// --- UI Update ---
function updateUI(s) {
  // Status badge
  const badge = document.getElementById('statusBadge');
  const statusText = document.getElementById('statusText');
  badge.className = 'status-badge status-' + (s.status || 'starting');
  statusText.textContent = (s.status || 'starting').charAt(0).toUpperCase() + (s.status || '').slice(1);

  // Meta info
  const meta = document.getElementById('metaInfo');
  meta.textContent = `${(s.exchange||'').toUpperCase()} | ${s.strategy || '--'} | ${s.timeframe || '--'} | Tick #${s.tick || 0}`;

  // Price ticker
  updateTicker(s.prices || {});

  // Portfolio cards
  updatePortfolioCards(s.portfolio || {});

  // Positions
  updatePositions(s.portfolio?.positions || {});

  // Signals (advanced)
  updateSignals(s.signals || []);

  // Trade log
  updateTrades(s.trade_log || []);

  // Equity chart (advanced)
  updateEquityChart(s.equity_curve || []);
}

function updateTicker(prices) {
  const el = document.getElementById('ticker');
  if (!Object.keys(prices).length) { el.innerHTML = '<div class="ticker-item"><span class="meta-text">Waiting for price data...</span></div>'; return; }
  el.innerHTML = Object.entries(prices).map(([pair, price]) =>
    `<div class="ticker-item">
      <span class="ticker-pair">${pair}</span>
      <span class="ticker-price">$${Number(price).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</span>
    </div>`
  ).join('');
}

function updatePortfolioCards(p) {
  const pnlClass = (p.total_pnl || 0) >= 0 ? 'positive' : 'negative';
  const pnlSign = (p.total_pnl || 0) >= 0 ? '+' : '';

  let html = `
    <div class="card">
      <div class="card-label">Portfolio Value</div>
      <div class="card-value neutral">$${(p.total_value || 0).toLocaleString(undefined,{minimumFractionDigits:2})}</div>
    </div>
    <div class="card">
      <div class="card-label">P&L</div>
      <div class="card-value ${pnlClass}">${pnlSign}$${(p.total_pnl || 0).toFixed(2)}</div>
      <div class="card-sub">${pnlSign}${(p.total_pnl_pct || 0).toFixed(2)}%</div>
    </div>
    <div class="card">
      <div class="card-label">Cash</div>
      <div class="card-value neutral">$${(p.cash || 0).toLocaleString(undefined,{minimumFractionDigits:2})}</div>
    </div>
    <div class="card">
      <div class="card-label">Open Positions</div>
      <div class="card-value neutral">${p.open_positions || 0}</div>
    </div>`;

  // Advanced-only cards
  html += `
    <div class="card advanced-only">
      <div class="card-label">Total Trades</div>
      <div class="card-value neutral">${p.total_trades || 0}</div>
    </div>`;

  document.getElementById('portfolioCards').innerHTML = html;
}

function updatePositions(positions) {
  const section = document.getElementById('positionsSection');
  const body = document.getElementById('positionsBody');
  const entries = Object.entries(positions);

  if (!entries.length) { section.style.display = 'none'; return; }
  section.style.display = 'block';

  body.innerHTML = entries.map(([pair, pos]) => {
    const pnlClass = (pos.unrealized_pnl || 0) >= 0 ? 'positive' : 'negative';
    const sign = (pos.unrealized_pnl || 0) >= 0 ? '+' : '';
    return `<tr>
      <td><strong>${pair}</strong></td>
      <td>${pos.quantity}</td>
      <td>$${(pos.entry_price||0).toLocaleString()}</td>
      <td>$${(pos.current_price||0).toLocaleString()}</td>
      <td class="${pnlClass}">${sign}$${(pos.unrealized_pnl||0).toFixed(2)} (${sign}${(pos.unrealized_pnl_pct||0).toFixed(2)}%)</td>
    </tr>`;
  }).join('');
}

function updateSignals(signals) {
  const body = document.getElementById('signalsBody');
  const recent = signals.slice(-15).reverse();
  body.innerHTML = recent.map(s => {
    const badgeClass = s.signal === 'BUY' ? 'badge-buy' : s.signal === 'SELL' ? 'badge-sell' : 'badge-hold';
    return `<tr>
      <td>${(s.time||'').slice(11,19)}</td>
      <td>${s.pair}</td>
      <td><span class="badge ${badgeClass}">${s.signal}</span></td>
      <td>${(s.confidence * 100).toFixed(0)}%</td>
      <td style="font-size:11px;color:#8b949e;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.reason}</td>
    </tr>`;
  }).join('');
}

function updateTrades(trades) {
  const body = document.getElementById('tradesBody');
  if (!trades.length) {
    body.innerHTML = '<tr><td colspan="6" style="color:#8b949e;text-align:center">No trades yet — waiting for signals...</td></tr>';
    return;
  }
  const recent = trades.slice(-20).reverse();
  body.innerHTML = recent.map(t => {
    const badgeClass = t.side === 'BUY' ? 'badge-buy' : 'badge-sell';
    return `<tr>
      <td>${(t.time||'').slice(11,19)}</td>
      <td>${t.pair}</td>
      <td><span class="badge ${badgeClass}">${t.side}</span></td>
      <td>$${(t.price||0).toLocaleString(undefined,{minimumFractionDigits:2})}</td>
      <td>$${(t.cost||0).toFixed(2)}</td>
      <td style="font-size:11px;color:#8b949e;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.reason||''}</td>
    </tr>`;
  }).join('');
}

function updateEquityChart(curve) {
  const canvas = document.getElementById('equityChart');
  if (!curve.length) return;

  const labels = curve.map(p => p.time ? p.time.slice(11, 19) : '');
  const data = curve.map(p => p.value);
  const startVal = data[0] || 10000;
  const isPositive = data[data.length - 1] >= startVal;

  if (equityChart) {
    equityChart.data.labels = labels;
    equityChart.data.datasets[0].data = data;
    equityChart.data.datasets[0].borderColor = isPositive ? '#3fb950' : '#f85149';
    equityChart.data.datasets[0].backgroundColor = isPositive ? 'rgba(63,185,80,0.08)' : 'rgba(248,81,73,0.08)';
    equityChart.data.datasets[1].data = labels.map(() => startVal);
    equityChart.update('none');
    return;
  }

  equityChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Portfolio ($)',
          data,
          borderColor: isPositive ? '#3fb950' : '#f85149',
          backgroundColor: isPositive ? 'rgba(63,185,80,0.08)' : 'rgba(248,81,73,0.08)',
          fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2,
        },
        {
          label: 'Starting Balance',
          data: labels.map(() => startVal),
          borderColor: '#30363d', borderDash: [5,5], pointRadius: 0, borderWidth: 1,
        }
      ]
    },
    options: {
      responsive: true,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#8b949e', font: { size: 11 } } },
        tooltip: {
          backgroundColor: '#161b22', borderColor: '#30363d', borderWidth: 1,
          titleColor: '#c9d1d9', bodyColor: '#e1e4e8',
          callbacks: { label: ctx => '$' + ctx.parsed.y.toLocaleString(undefined,{minimumFractionDigits:2}) }
        }
      },
      scales: {
        x: { ticks: { color: '#8b949e', maxTicksLimit: 10 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#8b949e', callback: v => '$' + v.toLocaleString() }, grid: { color: '#21262d' } }
      }
    }
  });
}

// --- Init ---
const savedMode = localStorage.getItem('dashboardMode') || 'simple';
setMode(savedMode);
fetchState();
setInterval(fetchState, 5000);  // poll every 5 seconds
</script>
</body>
</html>"""
