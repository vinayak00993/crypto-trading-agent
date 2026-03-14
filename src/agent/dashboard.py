"""
Dashboard Generator — creates a standalone HTML dashboard from backtest results.

Usage:
    python -m agent.run_backtest --compare --save-json
    python -m agent.dashboard

Opens a beautiful dashboard in your browser showing equity curves,
trade history, and strategy comparisons.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path

import structlog

from agent.config import PROJECT_ROOT

log = structlog.get_logger()


def generate_dashboard(results_path: Path | None = None) -> Path:
    """
    Generate an HTML dashboard from saved backtest results.

    Parameters
    ----------
    results_path : Path, optional
        Path to backtest_results.json. Defaults to data/backtest_results.json.

    Returns
    -------
    Path
        Path to the generated HTML file.
    """
    results_path = results_path or PROJECT_ROOT / "data" / "backtest_results.json"

    if not results_path.exists():
        print("❌ No backtest results found.")
        print("   Run a backtest first:")
        print("   python -m agent.run_backtest --compare --save-json")
        sys.exit(1)

    with open(results_path) as f:
        results = json.load(f)

    html = _build_html(results)

    output_path = PROJECT_ROOT / "data" / "dashboard.html"
    with open(output_path, "w") as f:
        f.write(html)

    return output_path


def _build_html(results: list[dict]) -> str:
    """Build the full HTML dashboard."""
    results_json = json.dumps(results, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Crypto Trading Agent — Backtest Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f1117;
    color: #e1e4e8;
    padding: 24px;
    line-height: 1.6;
  }}
  h1 {{
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 8px;
    background: linear-gradient(135deg, #58a6ff, #bc8cff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  .subtitle {{ color: #8b949e; margin-bottom: 32px; font-size: 14px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .card {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 20px;
  }}
  .card-label {{ font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }}
  .card-value {{ font-size: 28px; font-weight: 700; margin-top: 4px; }}
  .positive {{ color: #3fb950; }}
  .negative {{ color: #f85149; }}
  .neutral {{ color: #58a6ff; }}
  .section {{ margin-bottom: 40px; }}
  .section h2 {{ font-size: 20px; margin-bottom: 16px; color: #c9d1d9; }}
  .chart-container {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 24px;
  }}
  canvas {{ max-height: 400px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  th {{
    text-align: left;
    padding: 10px 12px;
    border-bottom: 2px solid #30363d;
    color: #8b949e;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
  }}
  td {{
    padding: 10px 12px;
    border-bottom: 1px solid #21262d;
  }}
  tr:hover {{ background: #1c2128; }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
  }}
  .badge-win {{ background: rgba(63,185,80,0.15); color: #3fb950; }}
  .badge-loss {{ background: rgba(248,81,73,0.15); color: #f85149; }}
  .strategy-tabs {{
    display: flex;
    gap: 8px;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }}
  .tab {{
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid #30363d;
    background: #161b22;
    color: #c9d1d9;
    cursor: pointer;
    font-size: 13px;
    transition: all 0.2s;
  }}
  .tab:hover {{ border-color: #58a6ff; }}
  .tab.active {{ background: #58a6ff; color: #0f1117; border-color: #58a6ff; font-weight: 600; }}
  .comparison-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
</style>
</head>
<body>

<h1>Crypto Trading Agent</h1>
<p class="subtitle">Backtest Dashboard — Paper Trading Performance</p>

<div id="app"></div>

<script>
const results = {results_json};

function render() {{
  const app = document.getElementById('app');

  if (!results || results.length === 0) {{
    app.innerHTML = '<p>No backtest results to display.</p>';
    return;
  }}

  // Strategy tabs
  let html = '<div class="strategy-tabs">';
  results.forEach((r, i) => {{
    html += `<div class="tab ${{i === 0 ? 'active' : ''}}" onclick="switchTab(${{i}})">${{r.strategy}}</div>`;
  }});
  html += '</div>';

  // Comparison cards (if multiple strategies)
  if (results.length > 1) {{
    html += '<div class="section"><h2>Strategy Comparison</h2><div class="comparison-row">';
    const sorted = [...results].sort((a, b) => b.metrics.total_return_pct - a.metrics.total_return_pct);
    sorted.forEach(r => {{
      const m = r.metrics;
      const retClass = m.total_return_pct >= 0 ? 'positive' : 'negative';
      html += `
        <div class="card">
          <div class="card-label">${{r.strategy}}</div>
          <div class="card-value ${{retClass}}">${{m.total_return_pct >= 0 ? '+' : ''}}${{m.total_return_pct}}%</div>
          <div style="margin-top:8px;font-size:12px;color:#8b949e">
            ${{m.total_trades}} trades · ${{m.win_rate}}% win rate · Sharpe ${{m.sharpe_ratio}}
          </div>
        </div>`;
    }});
    html += '</div></div>';
  }}

  // Per-strategy detail panels
  results.forEach((r, i) => {{
    html += `<div id="panel-${{i}}" style="display: ${{i === 0 ? 'block' : 'none'}}">`;
    html += renderStrategy(r, i);
    html += '</div>';
  }});

  app.innerHTML = html;

  // Render charts
  results.forEach((r, i) => {{
    if (r.equity_curve && r.equity_curve.length > 0) {{
      renderEquityChart(r, i);
    }}
  }});
}}

function renderStrategy(r, idx) {{
  const m = r.metrics;
  const retClass = m.total_return_pct >= 0 ? 'positive' : 'negative';

  let html = `
    <div class="section">
      <h2>${{r.strategy.toUpperCase()}} on ${{r.pair}}</h2>
      <div class="grid">
        <div class="card">
          <div class="card-label">Total Return</div>
          <div class="card-value ${{retClass}}">${{m.total_return_pct >= 0 ? '+' : ''}}${{m.total_return_pct}}%</div>
        </div>
        <div class="card">
          <div class="card-label">P&L</div>
          <div class="card-value ${{retClass}}">$${{m.total_pnl.toLocaleString()}}</div>
        </div>
        <div class="card">
          <div class="card-label">Win Rate</div>
          <div class="card-value neutral">${{m.win_rate}}%</div>
        </div>
        <div class="card">
          <div class="card-label">Sharpe Ratio</div>
          <div class="card-value ${{m.sharpe_ratio >= 1 ? 'positive' : m.sharpe_ratio < 0 ? 'negative' : 'neutral'}}">${{m.sharpe_ratio}}</div>
        </div>
        <div class="card">
          <div class="card-label">Max Drawdown</div>
          <div class="card-value negative">-${{m.max_drawdown_pct}}%</div>
        </div>
        <div class="card">
          <div class="card-label">Total Trades</div>
          <div class="card-value neutral">${{m.total_trades}}</div>
        </div>
        <div class="card">
          <div class="card-label">Profit Factor</div>
          <div class="card-value ${{m.profit_factor >= 1 ? 'positive' : 'negative'}}">${{m.profit_factor === Infinity ? '∞' : m.profit_factor}}</div>
        </div>
        <div class="card">
          <div class="card-label">Avg Hold Time</div>
          <div class="card-value neutral">${{m.avg_holding_period || 'N/A'}}</div>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="chart-container">
        <h2>Equity Curve</h2>
        <canvas id="equity-chart-${{idx}}"></canvas>
      </div>
    </div>`;

  // Trade history table
  if (r.trades && r.trades.length > 0) {{
    html += `
      <div class="section">
        <div class="card">
          <h2 style="margin-bottom:16px">Trade History</h2>
          <div style="overflow-x:auto">
            <table>
              <thead>
                <tr>
                  <th>Entry Time</th>
                  <th>Exit Time</th>
                  <th>Entry Price</th>
                  <th>Exit Price</th>
                  <th>P&L</th>
                  <th>Return</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>`;

    r.trades.forEach(t => {{
      const pnlClass = t.pnl >= 0 ? 'positive' : 'negative';
      const badge = t.pnl >= 0 ? 'badge-win' : 'badge-loss';
      html += `
                <tr>
                  <td>${{t.entry_time}}</td>
                  <td>${{t.exit_time || '—'}}</td>
                  <td>$${{t.entry_price.toLocaleString()}}</td>
                  <td>$${{(t.exit_price || 0).toLocaleString()}}</td>
                  <td class="${{pnlClass}}">$${{t.pnl.toFixed(2)}}</td>
                  <td><span class="badge ${{badge}}">${{t.pnl_pct >= 0 ? '+' : ''}}${{t.pnl_pct.toFixed(2)}}%</span></td>
                  <td style="font-size:11px;color:#8b949e;max-width:200px;overflow:hidden;text-overflow:ellipsis">${{t.reason_exit}}</td>
                </tr>`;
    }});

    html += '</tbody></table></div></div></div>';
  }}

  return html;
}}

function renderEquityChart(r, idx) {{
  const canvas = document.getElementById(`equity-chart-${{idx}}`);
  if (!canvas) return;

  const labels = r.equity_curve.map((_, i) => i);
  const startVal = r.equity_curve[0] || 10000;

  new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: labels,
      datasets: [
        {{
          label: 'Portfolio Value ($)',
          data: r.equity_curve,
          borderColor: r.metrics.total_return_pct >= 0 ? '#3fb950' : '#f85149',
          backgroundColor: r.metrics.total_return_pct >= 0
            ? 'rgba(63,185,80,0.1)'
            : 'rgba(248,81,73,0.1)',
          fill: true,
          tension: 0.3,
          pointRadius: 0,
          borderWidth: 2,
        }},
        {{
          label: 'Starting Balance',
          data: labels.map(() => startVal),
          borderColor: '#30363d',
          borderDash: [5, 5],
          pointRadius: 0,
          borderWidth: 1,
        }}
      ]
    }},
    options: {{
      responsive: true,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ labels: {{ color: '#8b949e' }} }},
        tooltip: {{
          backgroundColor: '#161b22',
          borderColor: '#30363d',
          borderWidth: 1,
          titleColor: '#c9d1d9',
          bodyColor: '#e1e4e8',
          callbacks: {{
            label: ctx => `$${{ctx.parsed.y.toLocaleString(undefined, {{minimumFractionDigits: 2}})}}`
          }}
        }}
      }},
      scales: {{
        x: {{
          display: false,
        }},
        y: {{
          ticks: {{ color: '#8b949e', callback: v => '$' + v.toLocaleString() }},
          grid: {{ color: '#21262d' }},
        }}
      }}
    }}
  }});
}}

function switchTab(idx) {{
  document.querySelectorAll('.tab').forEach((t, i) => {{
    t.classList.toggle('active', i === idx);
  }});
  results.forEach((_, i) => {{
    const panel = document.getElementById(`panel-${{i}}`);
    if (panel) panel.style.display = i === idx ? 'block' : 'none';
  }});
}}

render();
</script>
</body>
</html>"""


def main() -> None:
    """Generate and open the dashboard."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[structlog.dev.ConsoleRenderer()],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    path = generate_dashboard()
    print(f"📊 Dashboard generated: {path}")
    print("   Opening in browser...")
    webbrowser.open(f"file://{path}")


if __name__ == "__main__":
    main()
