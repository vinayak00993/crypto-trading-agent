"""
Live Dashboard Server — multi-pod version with per-strategy performance tracking.
"""

from __future__ import annotations

import json
import threading

from flask import Flask, Response

from agent.state import store

app = Flask(__name__)


@app.route("/")
def index() -> str:
    return DASHBOARD_HTML


@app.route("/api/state")
def api_state() -> Response:
    state = store.snapshot()
    return Response(json.dumps(state, default=str), mimetype="application/json")


def start_server(port: int = 5555) -> None:
    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto Trading Agent - Multi-Pod Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0e14; color: #e1e4e8; min-height: 100vh; }

  .header { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid #1c2128; background: #0d1117; }
  .header-left { display: flex; align-items: center; gap: 14px; }
  .logo { font-size: 20px; font-weight: 700; background: linear-gradient(135deg, #58a6ff, #bc8cff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .status-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
  .status-running { background: rgba(63,185,80,0.15); color: #3fb950; }
  .status-stopped { background: rgba(248,81,73,0.15); color: #f85149; }
  .status-starting { background: rgba(210,153,34,0.15); color: #d29922; }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; animation: pulse 2s infinite; }
  .status-running .status-dot { background: #3fb950; }
  .status-stopped .status-dot { background: #f85149; }
  .status-starting .status-dot { background: #d29922; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
  .header-right { display: flex; align-items: center; gap: 14px; }
  .meta-text { font-size: 11px; color: #8b949e; }
  .toggle-container { display: flex; background: #161b22; border-radius: 8px; border: 1px solid #30363d; overflow: hidden; }
  .toggle-btn { padding: 5px 14px; font-size: 11px; font-weight: 600; cursor: pointer; border: none; background: transparent; color: #8b949e; transition: all 0.2s; }
  .toggle-btn.active { background: #58a6ff; color: #0a0e14; }

  .container { padding: 20px 24px; max-width: 1400px; margin: 0 auto; }

  /* Price ticker */
  .ticker { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .ticker-item { display: flex; align-items: center; gap: 8px; background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 10px 16px; flex: 1; min-width: 180px; }
  .ticker-pair { font-weight: 600; font-size: 13px; }
  .ticker-price { font-size: 20px; font-weight: 700; }

  /* Cards */
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 14px; }
  .card-label { font-size: 10px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
  .card-value { font-size: 22px; font-weight: 700; margin-top: 2px; }
  .card-sub { font-size: 10px; color: #8b949e; margin-top: 2px; }
  .positive { color: #3fb950; }
  .negative { color: #f85149; }
  .neutral { color: #58a6ff; }

  /* Pod cards - the strategy comparison row */
  .pod-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .pod-card { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px; position: relative; }
  .pod-name { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; margin-bottom: 6px; }
  .pod-value { font-size: 24px; font-weight: 700; }
  .pod-detail { font-size: 11px; color: #8b949e; margin-top: 4px; }
  .pod-rank { position: absolute; top: 12px; right: 14px; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 6px; }
  .rank-1 { background: rgba(210,153,34,0.2); color: #d29922; }
  .rank-other { background: rgba(139,148,158,0.1); color: #8b949e; }

  /* Sections */
  .section { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px; margin-bottom: 16px; }
  .section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #c9d1d9; }
  canvas { max-height: 280px; }

  /* Table */
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; padding: 6px 8px; border-bottom: 2px solid #30363d; color: #8b949e; font-weight: 600; font-size: 10px; text-transform: uppercase; }
  td { padding: 6px 8px; border-bottom: 1px solid #21262d; }
  tr:hover { background: #1c2128; }
  .badge { display: inline-block; padding: 2px 6px; border-radius: 5px; font-size: 10px; font-weight: 600; }
  .badge-buy { background: rgba(63,185,80,0.15); color: #3fb950; }
  .badge-sell { background: rgba(248,81,73,0.15); color: #f85149; }
  .badge-hold { background: rgba(139,148,158,0.15); color: #8b949e; }
  .pod-tag { font-size: 9px; font-weight: 600; padding: 1px 5px; border-radius: 4px; background: rgba(88,166,255,0.15); color: #58a6ff; }

  .advanced-only { display: block; }
  body.simple-mode .advanced-only { display: none; }

  .refresh-bar { height: 2px; background: linear-gradient(90deg, transparent, #58a6ff, transparent); position: fixed; top: 0; left: 0; width: 100%; opacity: 0; transition: opacity 0.3s; }
  .refresh-bar.active { opacity: 1; animation: slide 1s linear; }
  @keyframes slide { from { transform: translateX(-100%); } to { transform: translateX(100%); } }
</style>
</head>
<body>
<div class="refresh-bar" id="refreshBar"></div>
<div class="header">
  <div class="header-left">
    <span class="logo">Crypto Trading Agent</span>
    <span class="status-badge status-starting" id="statusBadge"><span class="status-dot"></span><span id="statusText">Connecting...</span></span>
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
  <div class="ticker" id="ticker"></div>
  <div class="cards" id="portfolioCards"></div>
  <div class="pod-row" id="podRow"></div>
  <div class="section advanced-only" id="equitySection">
    <div class="section-title">Portfolio Value — Combined & Per-Strategy</div>
    <canvas id="equityChart"></canvas>
  </div>
  <div class="section" id="positionsSection" style="display:none">
    <div class="section-title">Open Positions</div>
    <table><thead><tr><th>Strategy</th><th>Pair</th><th>Qty</th><th>Entry</th><th>Current</th><th>P&L</th></tr></thead><tbody id="positionsBody"></tbody></table>
  </div>
  <div class="section advanced-only" id="signalsSection">
    <div class="section-title">Recent Strategy Signals</div>
    <table><thead><tr><th>Time</th><th>Strategy</th><th>Pair</th><th>Signal</th><th>Conf</th><th>Reason</th></tr></thead><tbody id="signalsBody"></tbody></table>
  </div>
  <div class="section" id="tradesSection">
    <div class="section-title">Trade History</div>
    <table><thead><tr><th>Time</th><th>Strategy</th><th>Pair</th><th>Side</th><th>Price</th><th>Cost</th></tr></thead><tbody id="tradesBody"></tbody></table>
  </div>
</div>
<script>
let equityChart = null;
let currentMode = 'simple';

const POD_COLORS = {
  // Technical (cool colors)
  sma_crossover: '#58a6ff', rsi: '#3fb950', macd: '#bc8cff', bollinger_bands: '#d29922',
  // Fundamental (warm colors)
  fear_greed: '#f85149', network_activity: '#f0883e', volume_momentum: '#db61a2', dca_baseline: '#8b949e'
};
const TECHNICAL = ['sma_crossover', 'rsi', 'macd', 'bollinger_bands'];
const FUNDAMENTAL = ['fear_greed', 'network_activity', 'volume_momentum', 'dca_baseline'];

function setMode(mode) {
  currentMode = mode;
  document.body.classList.toggle('simple-mode', mode === 'simple');
  document.getElementById('btnSimple').classList.toggle('active', mode === 'simple');
  document.getElementById('btnAdvanced').classList.toggle('active', mode === 'advanced');
}

async function fetchState() {
  try {
    document.getElementById('refreshBar').classList.add('active');
    const resp = await fetch('/api/state');
    const s = await resp.json();
    updateUI(s);
    setTimeout(() => document.getElementById('refreshBar').classList.remove('active'), 500);
  } catch (e) { console.error('Fetch failed:', e); }
}

function updateUI(s) {
  // Status
  const badge = document.getElementById('statusBadge');
  badge.className = 'status-badge status-' + (s.status || 'starting');
  document.getElementById('statusText').textContent = (s.status || 'starting').charAt(0).toUpperCase() + (s.status || '').slice(1);
  document.getElementById('metaInfo').textContent = `${(s.exchange||'').toUpperCase()} | multi-pod | ${s.timeframe || '--'} | Tick #${s.tick || 0}`;

  updateTicker(s.prices || {});
  updatePortfolioCards(s.portfolio || {});
  updatePodRow(s.pods || {});
  updatePositions(s.portfolio?.positions || {});
  updateSignals(s.signals || []);
  updateTrades(s.trade_log || []);
  updateEquityChart(s.equity_curve || [], s.pod_equity || {});
}

function updateTicker(prices) {
  const el = document.getElementById('ticker');
  if (!Object.keys(prices).length) { el.innerHTML = '<div class="ticker-item"><span class="meta-text">Waiting for prices...</span></div>'; return; }
  el.innerHTML = Object.entries(prices).map(([pair, price]) =>
    `<div class="ticker-item"><span class="ticker-pair">${pair}</span><span class="ticker-price">$${Number(price).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</span></div>`
  ).join('');
}

function updatePortfolioCards(p) {
  const pnlClass = (p.total_pnl || 0) >= 0 ? 'positive' : 'negative';
  const sign = (p.total_pnl || 0) >= 0 ? '+' : '';
  document.getElementById('portfolioCards').innerHTML = `
    <div class="card"><div class="card-label">Combined Value</div><div class="card-value neutral">$${(p.total_value||0).toLocaleString(undefined,{minimumFractionDigits:2})}</div></div>
    <div class="card"><div class="card-label">Combined P&L</div><div class="card-value ${pnlClass}">${sign}$${(p.total_pnl||0).toFixed(2)}</div><div class="card-sub">${sign}${(p.total_pnl_pct||0).toFixed(2)}%</div></div>
    <div class="card"><div class="card-label">Total Cash</div><div class="card-value neutral">$${(p.cash||0).toLocaleString(undefined,{minimumFractionDigits:2})}</div></div>
    <div class="card"><div class="card-label">Positions</div><div class="card-value neutral">${p.open_positions||0}</div></div>
    <div class="card advanced-only"><div class="card-label">Total Trades</div><div class="card-value neutral">${p.total_trades||0}</div></div>`;
}

function updatePodRow(pods) {
  const el = document.getElementById('podRow');
  const entries = Object.entries(pods);
  if (!entries.length) { el.innerHTML = ''; return; }

  // Sort by P&L for ranking
  const sorted = [...entries].sort((a, b) => (b[1].pnl_pct || 0) - (a[1].pnl_pct || 0));
  const rankMap = {};
  sorted.forEach(([name], i) => { rankMap[name] = i + 1; });

  const techPods = entries.filter(([name]) => TECHNICAL.includes(name));
  const fundPods = entries.filter(([name]) => FUNDAMENTAL.includes(name));

  function renderPods(list) {
    return list.map(([name, pod]) => {
      const pnlClass = (pod.pnl || 0) >= 0 ? 'positive' : 'negative';
      const sign = (pod.pnl || 0) >= 0 ? '+' : '';
      const rank = rankMap[name];
      const rankClass = rank === 1 ? 'rank-1' : 'rank-other';
      const color = POD_COLORS[name] || '#8b949e';
      return `<div class="pod-card" style="border-top: 3px solid ${color}">
        <span class="pod-rank ${rankClass}">#${rank}</span>
        <div class="pod-name">${name.replace(/_/g, ' ')}</div>
        <div class="pod-value ${pnlClass}">${sign}${(pod.pnl_pct||0).toFixed(2)}%</div>
        <div class="pod-detail">$${(pod.total_value||0).toLocaleString(undefined,{minimumFractionDigits:2})} | ${pod.total_trades||0} trades | ${pod.open_positions||0} open</div>
      </div>`;
    }).join('');
  }

  let html = '';
  if (techPods.length) html += `<div style="grid-column:1/-1;font-size:11px;font-weight:700;color:#58a6ff;text-transform:uppercase;letter-spacing:1px;margin-top:4px">Technical Strategies</div>` + renderPods(techPods);
  if (fundPods.length) html += `<div style="grid-column:1/-1;font-size:11px;font-weight:700;color:#f0883e;text-transform:uppercase;letter-spacing:1px;margin-top:8px">Fundamental Strategies</div>` + renderPods(fundPods);
  el.innerHTML = html;
}

function updatePositions(positions) {
  const section = document.getElementById('positionsSection');
  const body = document.getElementById('positionsBody');
  const entries = Object.entries(positions);
  if (!entries.length) { section.style.display = 'none'; return; }
  section.style.display = 'block';
  body.innerHTML = entries.map(([label, pos]) => {
    const pnlClass = (pos.unrealized_pnl||0) >= 0 ? 'positive' : 'negative';
    const sign = (pos.unrealized_pnl||0) >= 0 ? '+' : '';
    // label format: "BTC/USDT (sma_crossover)"
    const parts = label.match(/(.+) \((.+)\)/);
    const pair = parts ? parts[1] : label;
    const pod = parts ? parts[2] : '';
    return `<tr><td><span class="pod-tag">${pod}</span></td><td>${pair}</td><td>${pos.quantity}</td><td>$${(pos.entry_price||0).toLocaleString()}</td><td>$${(pos.current_price||0).toLocaleString()}</td><td class="${pnlClass}">${sign}$${(pos.unrealized_pnl||0).toFixed(2)}</td></tr>`;
  }).join('');
}

function updateSignals(signals) {
  const body = document.getElementById('signalsBody');
  const recent = signals.slice(-20).reverse();
  body.innerHTML = recent.map(s => {
    const bc = s.signal === 'BUY' ? 'badge-buy' : s.signal === 'SELL' ? 'badge-sell' : 'badge-hold';
    return `<tr><td>${(s.time||'').slice(11,19)}</td><td><span class="pod-tag">${s.pod||''}</span></td><td>${s.pair}</td><td><span class="badge ${bc}">${s.signal}</span></td><td>${((s.confidence||0)*100).toFixed(0)}%</td><td style="font-size:10px;color:#8b949e;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.reason||''}</td></tr>`;
  }).join('');
}

function updateTrades(trades) {
  const body = document.getElementById('tradesBody');
  if (!trades.length) { body.innerHTML = '<tr><td colspan="6" style="color:#8b949e;text-align:center">No trades yet...</td></tr>'; return; }
  body.innerHTML = trades.slice(-20).reverse().map(t => {
    const bc = t.side === 'BUY' ? 'badge-buy' : 'badge-sell';
    return `<tr><td>${(t.time||'').slice(11,19)}</td><td><span class="pod-tag">${t.pod||''}</span></td><td>${t.pair}</td><td><span class="badge ${bc}">${t.side}</span></td><td>$${(t.price||0).toLocaleString(undefined,{minimumFractionDigits:2})}</td><td>$${(t.cost||0).toFixed(2)}</td></tr>`;
  }).join('');
}

function updateEquityChart(combined, podEquity) {
  const canvas = document.getElementById('equityChart');
  if (!combined.length) return;

  const labels = combined.map(p => p.time ? p.time.slice(11, 19) : '');
  const combData = combined.map(p => p.value);
  const startVal = combData[0] || 10000;

  const datasets = [{
    label: 'Combined',
    data: combData,
    borderColor: '#e1e4e8',
    backgroundColor: 'rgba(225,228,232,0.05)',
    fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2.5,
  }];

  // Add per-pod lines
  Object.entries(podEquity).forEach(([name, points]) => {
    datasets.push({
      label: name.replace('_', ' '),
      data: points.map(p => p.value),
      borderColor: POD_COLORS[name] || '#8b949e',
      fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5, borderDash: [4, 2],
    });
  });

  // Starting balance line
  datasets.push({
    label: 'Starting',
    data: labels.map(() => startVal),
    borderColor: '#30363d', borderDash: [5,5], pointRadius: 0, borderWidth: 1,
  });

  if (equityChart) {
    equityChart.data.labels = labels;
    equityChart.data.datasets = datasets;
    equityChart.update('none');
    return;
  }

  equityChart = new Chart(canvas, {
    type: 'line', data: { labels, datasets },
    options: {
      responsive: true, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#8b949e', font: { size: 10 }, usePointStyle: true, pointStyle: 'line' } },
        tooltip: { backgroundColor: '#161b22', borderColor: '#30363d', borderWidth: 1, titleColor: '#c9d1d9', bodyColor: '#e1e4e8',
          callbacks: { label: ctx => `${ctx.dataset.label}: $${ctx.parsed.y.toLocaleString(undefined,{minimumFractionDigits:2})}` } }
      },
      scales: {
        x: { ticks: { color: '#8b949e', maxTicksLimit: 8 }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#8b949e', callback: v => '$' + v.toLocaleString() }, grid: { color: '#21262d' } }
      }
    }
  });
}

const savedMode = localStorage.getItem('dashMode') || 'simple';
setMode(savedMode);
document.getElementById('btnSimple').onclick = () => { setMode('simple'); localStorage.setItem('dashMode','simple'); };
document.getElementById('btnAdvanced').onclick = () => { setMode('advanced'); localStorage.setItem('dashMode','advanced'); };
fetchState();
setInterval(fetchState, 5000);
</script>
</body>
</html>"""
