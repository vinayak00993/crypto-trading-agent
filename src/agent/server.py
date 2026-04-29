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
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0a0e14;
    background-image:
      radial-gradient(ellipse at 20% 50%, rgba(88,166,255,0.04) 0%, transparent 50%),
      radial-gradient(ellipse at 80% 20%, rgba(188,140,255,0.03) 0%, transparent 50%),
      radial-gradient(ellipse at 50% 80%, rgba(63,185,80,0.02) 0%, transparent 50%);
    background-attachment: fixed;
    color: #e1e4e8;
    min-height: 100vh;
  }
  .mono { font-family: 'JetBrains Mono', monospace; }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: #484f58; }

  /* Header */
  .header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 28px;
    background: rgba(13,17,23,0.85);
    backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    border-bottom: 1px solid rgba(48,54,61,0.4);
    position: sticky; top: 0; z-index: 100;
  }
  .header-left { display: flex; align-items: center; gap: 14px; }
  .logo {
    font-size: 22px; font-weight: 800; letter-spacing: -0.5px;
    background: linear-gradient(135deg, #58a6ff 0%, #bc8cff 50%, #e3b341 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .status-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 600; }
  .status-running { background: rgba(63,185,80,0.12); color: #3fb950; }
  .status-stopped { background: rgba(248,81,73,0.12); color: #f85149; }
  .status-starting { background: rgba(210,153,34,0.12); color: #d29922; }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; animation: pulse 2s infinite; }
  .status-running .status-dot { background: #3fb950; }
  .status-stopped .status-dot { background: #f85149; }
  .status-starting .status-dot { background: #d29922; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  .header-right { display: flex; align-items: center; gap: 14px; }
  .meta-text { font-size: 11px; color: #484f58; font-weight: 500; }
  .toggle-container { display: flex; background: rgba(22,27,34,0.8); border-radius: 8px; border: 1px solid rgba(48,54,61,0.5); overflow: hidden; }
  .toggle-btn { padding: 5px 14px; font-size: 11px; font-weight: 600; cursor: pointer; border: none; background: transparent; color: #8b949e; transition: all 0.25s; font-family: 'Inter', sans-serif; }
  .toggle-btn.active { background: linear-gradient(135deg, #58a6ff, #bc8cff); color: #fff; font-weight: 700; }

  .container { padding: 20px 28px; max-width: 1440px; margin: 0 auto; }

  /* Price ticker */
  .ticker { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .ticker-item {
    display: flex; justify-content: space-between; align-items: center; gap: 12px;
    background: rgba(22,27,34,0.6);
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(48,54,61,0.5);
    border-radius: 12px; padding: 14px 20px; flex: 1; min-width: 200px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.03);
    transition: all 0.3s ease;
  }
  .ticker-item:hover { transform: translateY(-2px); box-shadow: 0 8px 32px rgba(0,0,0,0.25); border-color: rgba(88,166,255,0.2); }
  .ticker-pair { font-weight: 700; font-size: 14px; }
  .ticker-sub { font-size: 9px; color: #484f58; margin-top: 2px; letter-spacing: 1.5px; font-weight: 600; text-transform: uppercase; }
  .ticker-price { font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; transition: color 0.3s; }
  .ticker-change { font-size: 11px; margin-top: 2px; font-family: 'JetBrains Mono', monospace; }
  @keyframes flashGreen { 0% { box-shadow: 0 0 20px rgba(63,185,80,0.3); } 100% { box-shadow: 0 4px 24px rgba(0,0,0,0.15); } }
  @keyframes flashRed { 0% { box-shadow: 0 0 20px rgba(248,81,73,0.3); } 100% { box-shadow: 0 4px 24px rgba(0,0,0,0.15); } }
  .ticker-flash-up { animation: flashGreen 1s ease-out; border-color: rgba(63,185,80,0.4); }
  .ticker-flash-down { animation: flashRed 1s ease-out; border-color: rgba(248,81,73,0.4); }

  /* Cards */
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .card {
    background: rgba(22,27,34,0.6);
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(48,54,61,0.5);
    border-radius: 12px; padding: 16px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.03);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    position: relative; overflow: hidden;
  }
  .card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, #58a6ff, #bc8cff); opacity: 0.4;
  }
  .card:hover { transform: translateY(-2px); box-shadow: 0 8px 32px rgba(0,0,0,0.25); }
  .card-label { font-size: 10px; color: #484f58; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
  .card-value { font-size: 26px; font-weight: 700; margin-top: 4px; font-family: 'JetBrains Mono', monospace; }
  .card-sub { font-size: 11px; color: #8b949e; margin-top: 2px; font-family: 'JetBrains Mono', monospace; }
  .card-pnl-pos { background: linear-gradient(135deg, rgba(63,185,80,0.08), rgba(63,185,80,0.02)); border-color: rgba(63,185,80,0.25); }
  .card-pnl-neg { background: linear-gradient(135deg, rgba(248,81,73,0.08), rgba(248,81,73,0.02)); border-color: rgba(248,81,73,0.25); }
  .positive { color: #3fb950; }
  .negative { color: #f85149; }
  .neutral { color: #58a6ff; }

  /* Pod cards */
  .pod-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .pod-card {
    background: rgba(22,27,34,0.6);
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(48,54,61,0.5);
    border-radius: 12px; padding: 16px; position: relative;
    box-shadow: 0 4px 24px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.03);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    overflow: hidden;
  }
  .pod-card:hover { transform: translateY(-2px); box-shadow: 0 8px 32px rgba(0,0,0,0.25); }
  .pod-name { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; color: #8b949e; margin-bottom: 6px; }
  .pod-value { font-size: 26px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
  .pod-detail { font-size: 10px; color: #484f58; margin-top: 4px; font-weight: 500; }
  .pod-rank { position: absolute; top: 12px; right: 14px; font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 6px; font-family: 'JetBrains Mono', monospace; }
  .rank-1 { background: rgba(210,153,34,0.2); color: #e3b341; box-shadow: 0 0 12px rgba(210,153,34,0.15); }
  .rank-2 { background: rgba(139,148,158,0.15); color: #c9d1d9; }
  .rank-3 { background: rgba(210,105,30,0.15); color: #f0883e; }
  .rank-other { background: rgba(139,148,158,0.08); color: #8b949e; }
  .pod-pnl-bar { height: 3px; background: rgba(255,255,255,0.04); border-radius: 3px; margin: 8px 0 6px; overflow: hidden; }
  .pod-pnl-fill { height: 100%; border-radius: 3px; transition: width 0.5s ease; }
  .pod-pnl-fill.positive { background: linear-gradient(90deg, #3fb950, #56d364); }
  .pod-pnl-fill.negative { background: linear-gradient(90deg, #f85149, #da3633); }
  .pod-spark { width: 100%; height: 40px; margin-top: 8px; opacity: 0.7; display: block; }

  /* Group labels */
  .group-label {
    grid-column: 1 / -1;
    font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px;
    padding: 12px 0 4px;
    display: flex; align-items: center; gap: 10px;
  }
  .group-label::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, rgba(48,54,61,0.6), transparent);
  }

  /* Sections */
  .section {
    background: rgba(22,27,34,0.6);
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(48,54,61,0.5);
    border-radius: 12px; padding: 20px; margin-bottom: 16px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.03);
  }
  .section-title {
    font-size: 13px; font-weight: 700; margin-bottom: 16px; color: #e1e4e8;
    letter-spacing: -0.2px;
    display: flex; align-items: center; gap: 8px;
  }
  .section-title::before {
    content: ''; width: 3px; height: 16px;
    background: linear-gradient(180deg, #58a6ff, #bc8cff);
    border-radius: 2px;
  }
  canvas#equityChart { max-height: 300px; }

  /* Table */
  table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }
  th {
    text-align: left; padding: 10px 12px;
    border-bottom: 1px solid rgba(48,54,61,0.6);
    color: #484f58; font-weight: 600; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.8px;
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid rgba(33,38,45,0.5);
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
  }
  tr { transition: background 0.15s ease; }
  tr:hover { background: rgba(88,166,255,0.04); }
  .badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 8px; border-radius: 6px;
    font-size: 10px; font-weight: 700; letter-spacing: 0.5px;
    text-transform: uppercase; font-family: 'Inter', sans-serif;
  }
  .badge-buy { background: rgba(63,185,80,0.12); color: #56d364; box-shadow: 0 0 8px rgba(63,185,80,0.1); }
  .badge-sell { background: rgba(248,81,73,0.12); color: #f97583; box-shadow: 0 0 8px rgba(248,81,73,0.1); }
  .badge-hold { background: rgba(139,148,158,0.08); color: #8b949e; }
  .pod-tag {
    font-size: 9px; font-weight: 600; padding: 2px 7px; border-radius: 4px;
    background: rgba(88,166,255,0.1); color: #58a6ff;
    font-family: 'JetBrains Mono', monospace;
  }

  .advanced-only { display: block; }
  body.simple-mode .advanced-only { display: none; }

  /* Empty state */
  .empty-state { text-align: center; padding: 32px 16px; color: #484f58; font-size: 13px; }
  .empty-state-icon { font-size: 28px; margin-bottom: 8px; opacity: 0.5; }

  /* Refresh bar */
  .refresh-bar {
    height: 2px;
    background: linear-gradient(90deg, transparent 0%, #58a6ff 30%, #bc8cff 70%, transparent 100%);
    position: fixed; top: 0; left: 0; width: 100%;
    opacity: 0; z-index: 200; transition: opacity 0.2s;
  }
  .refresh-bar.active { opacity: 1; animation: shimmer 1.5s ease-in-out; }
  @keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }

  /* Value flash */
  @keyframes valueFlash { 0% { color: #58a6ff; } 100% { color: inherit; } }
  .value-updated { animation: valueFlash 0.5s ease-out; }
</style>
</head>
<body>
<div class="refresh-bar" id="refreshBar"></div>
<div class="header">
  <div class="header-left">
    <span class="logo">&#9889; Crypto Trading Agent</span>
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
let prevPrices = {};
let prevPortfolio = {};
let lastPodEquity = {};

const POD_COLORS = {
  sma_crossover: '#58a6ff', rsi: '#3fb950', macd: '#bc8cff', bollinger_bands: '#d29922',
  fear_greed: '#f85149', network_activity: '#f0883e', volume_momentum: '#db61a2', dca_baseline: '#8b949e',
  ml_meta_learner: '#e3b341'
};
const TECHNICAL = ['sma_crossover', 'rsi', 'macd', 'bollinger_bands'];
const FUNDAMENTAL = ['fear_greed', 'network_activity', 'volume_momentum', 'dca_baseline'];
const ML = ['ml_meta_learner'];

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
  lastPodEquity = s.pod_equity || {};
  drawSparklines(lastPodEquity);
}

function updateTicker(prices) {
  const el = document.getElementById('ticker');
  if (!Object.keys(prices).length) {
    el.innerHTML = '<div class="ticker-item"><span class="meta-text">Waiting for prices...</span></div>';
    return;
  }
  el.innerHTML = Object.entries(prices).map(([pair, price]) => {
    const prev = prevPrices[pair];
    const direction = prev ? (price > prev ? 'up' : price < prev ? 'down' : '') : '';
    const arrow = direction === 'up' ? '&#9650;' : direction === 'down' ? '&#9660;' : '';
    const dirClass = direction === 'up' ? 'positive' : direction === 'down' ? 'negative' : '';
    const flashClass = direction ? 'ticker-flash-' + direction : '';
    return `<div class="ticker-item ${flashClass}">
      <div><div class="ticker-pair">${pair}</div><div class="ticker-sub">Spot</div></div>
      <div style="text-align:right">
        <div class="ticker-price ${dirClass}">$${Number(price).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</div>
        <div class="ticker-change ${dirClass}">${arrow}</div>
      </div>
    </div>`;
  }).join('');
  prevPrices = {...prices};
}

function updatePortfolioCards(p) {
  const pnlClass = (p.total_pnl || 0) >= 0 ? 'positive' : 'negative';
  const pnlCardClass = (p.total_pnl || 0) >= 0 ? 'card-pnl-pos' : 'card-pnl-neg';
  const sign = (p.total_pnl || 0) >= 0 ? '+' : '';
  document.getElementById('portfolioCards').innerHTML = `
    <div class="card"><div class="card-label">Combined Value</div><div class="card-value neutral">$${(p.total_value||0).toLocaleString(undefined,{minimumFractionDigits:2})}</div></div>
    <div class="card ${pnlCardClass}"><div class="card-label">Combined P&L</div><div class="card-value ${pnlClass}">${sign}$${(p.total_pnl||0).toFixed(2)}</div><div class="card-sub">${sign}${(p.total_pnl_pct||0).toFixed(2)}%</div></div>
    <div class="card"><div class="card-label">Total Cash</div><div class="card-value neutral">$${(p.cash||0).toLocaleString(undefined,{minimumFractionDigits:2})}</div></div>
    <div class="card"><div class="card-label">Positions</div><div class="card-value neutral">${p.open_positions||0}</div></div>
    <div class="card advanced-only"><div class="card-label">Total Trades</div><div class="card-value neutral">${(p.total_trades||0).toLocaleString()}</div></div>`;
  prevPortfolio = p;
}

function updatePodRow(pods) {
  const el = document.getElementById('podRow');
  const entries = Object.entries(pods);
  if (!entries.length) { el.innerHTML = ''; return; }

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
      const rankClass = rank === 1 ? 'rank-1' : rank === 2 ? 'rank-2' : rank === 3 ? 'rank-3' : 'rank-other';
      const color = POD_COLORS[name] || '#8b949e';
      const barWidth = Math.min(Math.abs(pod.pnl_pct || 0) * 5, 100);
      return `<div class="pod-card" style="border-left: 3px solid ${color}">
        <span class="pod-rank ${rankClass}">#${rank}</span>
        <div class="pod-name">${name.replace(/_/g, ' ')}</div>
        <div class="pod-value ${pnlClass}">${sign}${(pod.pnl_pct||0).toFixed(2)}%</div>
        <div class="pod-pnl-bar"><div class="pod-pnl-fill ${pnlClass}" style="width:${barWidth}%"></div></div>
        <div class="pod-detail">${(pod.total_trades||0).toLocaleString()} trades &middot; ${pod.open_positions||0} open &middot; $${(pod.total_value||0).toFixed(0)}</div>
        <canvas class="pod-spark" id="spark_${name}" width="200" height="40"></canvas>
      </div>`;
    }).join('');
  }

  let html = '';
  if (techPods.length) html += `<div class="group-label" style="color:#58a6ff">Technical Strategies</div>` + renderPods(techPods);
  if (fundPods.length) html += `<div class="group-label" style="color:#f0883e">Fundamental Strategies</div>` + renderPods(fundPods);
  const mlPods = entries.filter(([name]) => ML.includes(name));
  if (mlPods.length) html += `<div class="group-label" style="color:#e3b341">ML Meta-Learner (Autonomous)</div>` + renderPods(mlPods);
  el.innerHTML = html;
}

function drawSparklines(podEquity) {
  Object.entries(podEquity).forEach(([name, points]) => {
    const canvas = document.getElementById('spark_' + name);
    if (!canvas || !points.length) return;
    const ctx = canvas.getContext('2d');
    const vals = points.map(p => p.value);
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = max - min || 1;
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    const color = POD_COLORS[name] || '#8b949e';

    // Gradient fill
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, color + '30');
    grad.addColorStop(1, color + '00');
    ctx.beginPath();
    ctx.moveTo(0, h);
    vals.forEach((v, i) => {
      const x = (i / (vals.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      ctx.lineTo(x, y);
    });
    ctx.lineTo(w, h);
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    vals.forEach((v, i) => {
      const x = (i / (vals.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  });
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
    return `<tr><td>${(s.time||'').slice(11,19)}</td><td><span class="pod-tag">${s.pod||''}</span></td><td>${s.pair}</td><td><span class="badge ${bc}">${s.signal}</span></td><td>${((s.confidence||0)*100).toFixed(0)}%</td><td style="font-size:10px;color:#484f58;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.reason||''}</td></tr>`;
  }).join('');
}

function updateTrades(trades) {
  const body = document.getElementById('tradesBody');
  if (!trades.length) {
    body.innerHTML = '<tr><td colspan="6"><div class="empty-state"><div class="empty-state-icon">&#128202;</div>No trades yet</div></td></tr>';
    return;
  }
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

  // Create gradient for combined line
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 300);
  gradient.addColorStop(0, 'rgba(88,166,255,0.15)');
  gradient.addColorStop(1, 'rgba(88,166,255,0.0)');

  const datasets = [{
    label: 'Combined',
    data: combData,
    borderColor: '#58a6ff',
    backgroundColor: gradient,
    fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2.5,
    pointHoverRadius: 4, pointHoverBackgroundColor: '#58a6ff',
  }];

  Object.entries(podEquity).forEach(([name, points]) => {
    datasets.push({
      label: name.replace(/_/g, ' '),
      data: points.map(p => p.value),
      borderColor: POD_COLORS[name] || '#8b949e',
      fill: false, tension: 0.4, pointRadius: 0, borderWidth: 1.5, borderDash: [4, 2],
    });
  });

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
        legend: {
          labels: {
            color: '#8b949e',
            font: { size: 10, family: 'Inter' },
            usePointStyle: true, pointStyle: 'circle', padding: 16
          }
        },
        tooltip: {
          backgroundColor: 'rgba(22,27,34,0.95)',
          borderColor: 'rgba(88,166,255,0.3)', borderWidth: 1,
          titleColor: '#c9d1d9', bodyColor: '#e1e4e8',
          titleFont: { family: 'Inter', weight: '600' },
          bodyFont: { family: 'JetBrains Mono', size: 12 },
          padding: 12, cornerRadius: 8, displayColors: true,
          callbacks: { label: ctx => ` ${ctx.dataset.label}: $${ctx.parsed.y.toLocaleString(undefined,{minimumFractionDigits:2})}` }
        }
      },
      scales: {
        x: {
          ticks: { color: '#484f58', maxTicksLimit: 8, font: { size: 10, family: 'Inter' } },
          grid: { color: 'rgba(48,54,61,0.3)', drawBorder: false }
        },
        y: {
          ticks: { color: '#484f58', callback: v => '$' + v.toLocaleString(), font: { size: 10, family: 'JetBrains Mono' } },
          grid: { color: 'rgba(48,54,61,0.3)', drawBorder: false }
        }
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
