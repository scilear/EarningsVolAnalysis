"""HTML report generation."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template


TEMPLATE = Template(
    """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>NVDA Earnings Volatility Report</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; color: #1b1b1b; }
    h1, h2 { color: #16334c; }
    table { border-collapse: collapse; width: 100%; margin: 16px 0; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background-color: #f3f6f9; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .note { font-size: 0.9em; color: #4a4a4a; }
  </style>
</head>
<body>
  <h1>NVDA Earnings Volatility Report</h1>
  <p><strong>Spot:</strong> {{ spot }}</p>
  <p><strong>Event Date:</strong> {{ event_date }}</p>
  <p><strong>Front Expiry:</strong> {{ front_expiry }}</p>

  <div class="grid">
    <div>
      <h2>Move Comparison</h2>
      <img src="data:image/png;base64,{{ move_plot }}" alt="move plot" />
    </div>
    <div>
      <h2>Top Strategy P&L</h2>
      <img src="data:image/png;base64,{{ pnl_plot }}" alt="pnl plot" />
    </div>
  </div>

  <h2>Vol Diagnostics</h2>
  <table>
    <tr><th>Implied Move</th><td>{{ implied_move }}</td></tr>
    <tr><th>Historical P75</th><td>{{ historical_p75 }}</td></tr>
    <tr><th>Event Vol</th><td>{{ event_vol }}</td></tr>
    <tr><th>Event Vol / Front IV</th><td>{{ event_vol_ratio }}</td></tr>
  </table>

  <h2>Skew Metrics</h2>
  <table>
    <tr><th>RR25</th><td>{{ rr25 }}</td></tr>
    <tr><th>BF25</th><td>{{ bf25 }}</td></tr>
  </table>

  <h2>Event Variance Diagnostics</h2>
  <table>
    <tr><th>Raw Event Var</th><td>{{ raw_event_var }}</td></tr>
    <tr><th>Ratio</th><td>{{ event_var_ratio }}</td></tr>
    <tr><th>Warning Level</th><td>{{ warning_level }}</td></tr>
    <tr><th>Assumption</th><td>{{ assumption }}</td></tr>
  </table>

  <h2>Slippage Sensitivity</h2>
  <table>
    <tr><th>EV (Base)</th><td>{{ ev_base }}</td></tr>
    <tr><th>EV (2x Slippage)</th><td>{{ ev_2x }}</td></tr>
  </table>

  <h2>Gamma Exposure</h2>
  <table>
    <tr><th>Net GEX</th><td>{{ net_gex }}</td></tr>
    <tr><th>Abs GEX</th><td>{{ abs_gex }}</td></tr>
  </table>
  <p class="note">GEX sign assumes dealers net short options. Interpret regime directionally.</p>
  {% if gex_note %}
  <p class="note">{{ gex_note }}</p>
  {% endif %}

  <h2>Strategy Rankings</h2>
  <table>
    <tr>
      <th>Rank</th>
      <th>Strategy</th>
      <th>Score</th>
      <th>EV</th>
      <th>CVaR</th>
      <th>Convexity</th>
      <th>Capital Ratio</th>
      <th>Risk</th>
    </tr>
    {% for row in rankings %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ row.strategy }}</td>
      <td>{{ row.score }}</td>
      <td>{{ row.ev }}</td>
      <td>{{ row.cvar }}</td>
      <td>{{ row.convexity }}</td>
      <td>{{ row.capital_ratio }}</td>
      <td>{{ row.risk_classification }}</td>
    </tr>
    {% endfor %}
  </table>
</body>
</html>
"""
)


def write_report(output_path: Path, context: dict) -> None:
    """Render and write HTML report to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = TEMPLATE.render(**context)
    output_path.write_text(content, encoding="utf-8")
