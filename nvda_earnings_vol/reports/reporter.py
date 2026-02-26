"""HTML report generation with enhanced sections."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, BaseLoader


def format_gex(value):
    """Format large GEX values with B/M suffix."""
    if value is None:
        return "N/A"
    abs_val = abs(float(value))
    sign = "-" if float(value) < 0 else ""
    if abs_val >= 1e9:
        return f"{sign}{abs_val/1e9:.2f}B"
    elif abs_val >= 1e6:
        return f"{sign}{abs_val/1e6:.2f}M"
    else:
        return f"{sign}{abs_val:.0f}"


# Create Jinja2 environment with custom filters
_jinja_env = Environment(loader=BaseLoader())
_jinja_env.filters["format_gex"] = format_gex


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>NVDA Earnings Volatility Report</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; color: #1b1b1b; background: #fafafa; }
    h1 { color: #16334c; border-bottom: 3px solid #16334c; padding-bottom: 12px; }
    h2 { color: #16334c; margin-top: 32px; border-bottom: 1px solid #ddd; padding-bottom: 8px; }
    h3 { color: #2c5282; }
    h4 { color: #4a5568; margin-top: 20px; }
    table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 0.95em; }
    th, td { border: 1px solid #cbd5e0; padding: 10px 12px; text-align: left; }
    th { background-color: #edf2f7; font-weight: 600; }
    tr:nth-child(even) { background-color: #f7fafc; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 24px 0; }
    .note { font-size: 0.9em; color: #4a5568; background: #fffaf0; padding: 12px; border-left: 4px solid #ed8936; margin: 12px 0; }
    .regime-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin: 24px 0; }
    .regime-summary { background: #f7fafc; padding: 16px; border-radius: 8px; border: 1px solid #e2e8f0; margin: 16px 0; }
    .regime-strength { background: #fffaf0; padding: 16px; border-radius: 8px; border-left: 4px solid #ed8936; margin: 16px 0; }
    .trade-sheet { border: 2px solid #2c5282; padding: 24px; margin-bottom: 40px; border-radius: 8px; background: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    .heatmap-cell { text-align: center; padding: 16px; font-weight: bold; color: white; border-radius: 4px; }
    .highlight-row { background: #1a202c !important; color: white !important; }
    .highlight-row td { color: white !important; }
    .strategy-header { background: #2c5282; color: white; padding: 12px 16px; border-radius: 4px; margin-bottom: 16px; }
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }
    .metric-box { background: #edf2f7; padding: 12px; border-radius: 4px; text-align: center; }
    .metric-label { font-size: 0.8em; color: #718096; text-transform: uppercase; }
    .metric-value { font-size: 1.2em; font-weight: bold; color: #2d3748; }
    details { margin: 12px 0; }
    summary { cursor: pointer; font-weight: 600; color: #4a5568; padding: 8px 12px;
              background: #edf2f7; border-radius: 4px; user-select: none; }
    summary:hover { background: #e2e8f0; }
    details[open] summary { border-radius: 4px 4px 0 0; }
    .rationale-body { background: #f7fafc; border: 1px solid #e2e8f0;
                      border-top: none; border-radius: 0 0 4px 4px;
                      padding: 12px 16px; font-size: 0.95em; color: #4a5568;
                      line-height: 1.6; }
    .not-applicable { background: #fff5f5; border-left: 4px solid #fc8181;
                      padding: 10px 16px; margin: 8px 0; border-radius: 0 4px 4px 0; }
    .not-applicable strong { color: #c53030; }
    .not-applicable small { color: #718096; }
  </style>
</head>
<body>
  <h1>NVDA Earnings Volatility Report</h1>
  
  <div class="metric-grid">
    <div class="metric-box">
      <div class="metric-label">Spot</div>
      <div class="metric-value">${{ "%.2f" | format(snapshot.spot) }}</div>
    </div>
    <div class="metric-box">
      <div class="metric-label">Event Date</div>
      <div class="metric-value">{{ snapshot.event_date }}</div>
    </div>
    <div class="metric-box">
      <div class="metric-label">Front Expiry</div>
      <div class="metric-value">{{ snapshot.front_expiry }}</div>
    </div>
    <div class="metric-box">
      <div class="metric-label">Back Expiry</div>
      <div class="metric-value">{{ snapshot.back_expiry }}</div>
    </div>
  </div>

  <div class="regime-header">
    <h2 style="margin: 0; border: none; color: white;">Regime Classification Engine</h2>
    <p style="margin: 8px 0 0 0; opacity: 0.9;">Market environment classification with confidence scoring</p>
  </div>

  <div class="regime-summary">
    <table>
      <tr>
        <th>Vol Pricing Regime</th>
        <td>{{ snapshot.regime.vol_regime }}</td>
        <th>Signal Strength</th>
        <td>{{ "%.2f" | format(snapshot.regime.vol_confidence) }}</td>
      </tr>
      <tr>
        <th>Event Structure</th>
        <td>{{ snapshot.regime.event_regime }}</td>
        <th>Signal Strength</th>
        <td>{{ "%.2f" | format(snapshot.regime.event_confidence) }}</td>
      </tr>
      <tr>
        <th>Term Structure</th>
        <td>{{ snapshot.regime.term_structure_regime }}</td>
        <th>—</th>
        <td>—</td>
      </tr>
      <tr>
        <th>Dealer Gamma Regime</th>
        <td>{{ snapshot.regime.gamma_regime }}</td>
        <th>Signal Strength</th>
        <td>{{ "%.2f" | format(snapshot.regime.gamma_confidence) }}</td>
      </tr>
      <tr class="highlight-row">
        <th>Composite Event Regime</th>
        <td><strong>{{ snapshot.regime.composite_regime }}</strong></td>
        <th>Composite Confidence</th>
        <td><strong>{{ "%.2f" | format(snapshot.regime.confidence) }}</strong></td>
      </tr>
    </table>
  </div>

  <h2>Volatility Regime Summary</h2>

  <table>
    <tr>
      <th>Spot</th>
      <td>${{ "%.2f" | format(snapshot.spot) }}</td>
      <th>Expected Move ($)</th>
      <td>${{ "%.2f" | format(snapshot.implied_move * snapshot.spot) }}</td>
    </tr>
    <tr>
      <th>Implied Move</th>
      <td>{{ "%.2f" | format(snapshot.implied_move * 100) }}%</td>
      <th>Historical P75</th>
      <td>{{ "%.2f" | format(snapshot.historical_p75 * 100) }}%</td>
    </tr>
    <tr>
      <th>Implied / P75</th>
      <td>{{ "%.3f" | format(snapshot.regime.vol_ratio) }}</td>
      <th>Vol Regime</th>
      <td><strong>{{ snapshot.regime.vol_regime }}</strong></td>
    </tr>
  </table>

  <h4>Term Structure Diagnostics</h4>
  <table>
    <tr>
      <th>Front IV</th>
      <td>{{ "%.2f" | format(snapshot.front_iv * 100) }}%</td>
      <th>Back1 IV</th>
      <td>{{ "%.2f" | format(snapshot.back_iv * 100) }}%</td>
      {% if snapshot.back2_iv %}
      <th>Back2 IV</th>
      <td>{{ "%.2f" | format(snapshot.back2_iv * 100) }}%</td>
      {% endif %}
    </tr>
    <tr>
      <th>Front–Back Spread</th>
      <td>{{ "%.2f" | format(snapshot.front_back_spread * 100) }} vol pts</td>
      <th>Term Structure</th>
      <td colspan="{% if snapshot.back2_iv %}4{% else %}2{% endif %}">{{ snapshot.regime.term_structure_regime }}</td>
    </tr>
  </table>

  <h4>Event Variance Attribution</h4>
  <table>
    <tr>
      <th>Raw Event Var</th>
      <td>{{ "%.6f" | format(snapshot.raw_event_var) }}</td>
      <th>EventVar / TotalFrontVar</th>
      <td>{{ "%.1f" | format(snapshot.event_variance_ratio * 100) }}%</td>
    </tr>
    <tr>
      <th>Event Structure</th>
      <td><strong>{{ snapshot.regime.event_regime }}</strong></td>
      <th>Interpolation Method</th>
      <td>{{ snapshot.interpolation_method }}</td>
    </tr>
    {% if snapshot.negative_event_var %}
    <tr>
      <td colspan="4" style="color: #c53030; background: #fff5f5;">
        <strong>⚠ Negative event variance detected — term structure may be inverted or data issue present.</strong>
      </td>
    </tr>
    {% endif %}
  </table>

  <h4>Historical Distribution</h4>
  <table>
    <tr>
      <th>Mean |Move|</th>
      <td>{{ "%.2f" | format(snapshot.mean_abs_move * 100) }}%</td>
      <th>Median |Move|</th>
      <td>{{ "%.2f" | format(snapshot.median_abs_move * 100) }}%</td>
    </tr>
    <tr>
      <th>Skewness</th>
      <td>{{ "%.3f" | format(snapshot.skewness) }}</td>
      <th>Excess Kurtosis</th>
      <td>{{ "%.3f" | format(snapshot.kurtosis) }}</td>
    </tr>
  </table>

  {% if snapshot.tail_probs %}
  <h4>Tail Probability Table</h4>
  <table>
    <tr>
      {% for threshold, prob in snapshot.tail_probs.items() %}
      <th>P(|Move| &gt; {{ (threshold * 100) | int }}%)</th>
      {% endfor %}
    </tr>
    <tr>
      {% for threshold, prob in snapshot.tail_probs.items() %}
      <td>{{ "%.1f" | format(prob * 100) }}%</td>
      {% endfor %}
    </tr>
  </table>
  {% endif %}

  <h2>Dealer Positioning & Microstructure</h2>

  <table>
    <tr>
      <th>Net GEX</th>
      <td>{{ snapshot.gex_net | format_gex }}</td>
      <th>Abs GEX</th>
      <td>{{ snapshot.gex_abs | format_gex }}</td>
    </tr>
    <tr>
      <th>Gamma Regime</th>
      <td>{{ snapshot.regime.gamma_regime }}</td>
      <th>Flip Level</th>
      <td>
        {% if snapshot.gamma_flip %}
          ${{ "%.2f" | format(snapshot.gamma_flip) }} ({{ "%.2f" | format(snapshot.flip_distance_pct) }}% from spot)
        {% else %}
          No flip detected in chain
        {% endif %}
      </td>
    </tr>
  </table>

  <p class="note">{{ snapshot.gex_dealer_note }}</p>

  <h4>Top 3 Strikes by Gamma Concentration</h4>
  <table>
    <tr>
      <th>Strike</th>
      <th>GEX</th>
      <th>% of Abs GEX</th>
    </tr>
    {% for strike, value in snapshot.top_gamma_strikes %}
    <tr>
      <td>${{ "%.2f" | format(strike) }}</td>
      <td>{{ value | format_gex }}</td>
      <td>{{ "%.1f" | format((value | abs) / snapshot.gex_abs * 100) }}%</td>
    </tr>
    {% endfor %}
  </table>

  <div class="grid">
    <div>
      <h2>Move Comparison</h2>
      <img src="data:image/png;base64,{{ move_plot }}" alt="move plot" style="max-width: 100%;" />
    </div>
    <div>
      <h2>Top Strategy P&L</h2>
      <img src="data:image/png;base64,{{ pnl_plot }}" alt="pnl plot" style="max-width: 100%;" />
    </div>
  </div>

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
      <th>Alignment</th>
      <th>Risk</th>
    </tr>
    {% for row in rankings %}
    <tr>
      <td>{{ row.rank }}</td>
      <td>{{ row.name }}</td>
      <td>{{ "%.4f" | format(row.score) }}</td>
      <td>${{ "%.2f" | format(row.ev) }}</td>
      <td>${{ "%.2f" | format(row.cvar) }}</td>
      <td>{{ "%.4f" | format(row.convexity) }}</td>
      <td>{{ "%.4f" | format(row.capital_ratio) }}</td>
      <td>{{ "%.2f" | format(row.alignment.alignment_score) }}</td>
      <td>{{ row.risk_classification }}</td>
    </tr>
    {% endfor %}
  </table>

  {% if not_applicable %}
  <h3>Conditional Strategies — Not Evaluated</h3>
  <p style="color: #718096; font-size: 0.9em;">
    The following strategies have entry-condition gates and were
    not activated for this market snapshot.
  </p>
  {% for item in not_applicable %}
  <div class="not-applicable">
    <strong>{{ item.name }}</strong>
    <small> — {{ item.reason }}</small>
  </div>
  {% endfor %}
  {% endif %}

  {% if post_event_calendar %}
  <h2>Post-Event Calendar Spread</h2>
  <div class="trade-sheet">
    <div class="strategy-header">
      <h3 style="margin: 0; font-size: 1.3em;">
        POST_EVENT_CALENDAR
      </h3>
      <span style="opacity: 0.9;">
        Deterministic scenario evaluation
        (not MC-scored)
      </span>
    </div>

    <h4>Structure</h4>
    <table>
      <tr>
        <th>Side</th><th>Type</th>
        <th>Strike</th><th>Expiry</th>
        <th>Entry $</th><th>IV</th>
      </tr>
      {% for leg in post_event_calendar.strategy.legs %}
      <tr>
        <td><strong>{{ leg.side | upper }}</strong></td>
        <td>{{ leg.option_type | upper }}</td>
        <td>${{ "%.2f" | format(leg.strike) }}</td>
        <td>{{ leg.expiry.strftime('%Y-%m-%d') }}</td>
        <td>
          {% if leg.entry_price %}
            ${{ "%.2f" | format(leg.entry_price) }}
          {% else %}—{% endif %}
        </td>
        <td>
          {% if leg.iv %}
            {{ "%.1f" | format(leg.iv * 100) }}%
          {% else %}—{% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>

    <h4>Entry Pricing</h4>
    <div class="metric-grid">
      <div class="metric-box">
        <div class="metric-label">Short Premium</div>
        <div class="metric-value">
          ${{ "%.2f" | format(
            post_event_calendar.details.short_premium
          ) }}
        </div>
      </div>
      <div class="metric-box">
        <div class="metric-label">Long Cost</div>
        <div class="metric-value">
          ${{ "%.2f" | format(
            post_event_calendar.details.long_cost
          ) }}
        </div>
      </div>
      <div class="metric-box">
        <div class="metric-label">Net Debit</div>
        <div class="metric-value" style="color: #c53030;">
          ${{ "%.2f" | format(
            post_event_calendar.details.net_cost
          ) }}
        </div>
      </div>
      <div class="metric-box">
        <div class="metric-label">IV Ratio</div>
        <div class="metric-value">
          {{ "%.2f" | format(
            snapshot.iv_ratio
          ) }}
        </div>
      </div>
    </div>

    <h4>Scenario P&amp;L at Front Expiry</h4>
    <table>
      <tr>
        {% for label in post_event_calendar.scenarios.keys() %}
        <th>{{ label | replace('_', ' ') | title }}</th>
        {% endfor %}
      </tr>
      <tr>
        {% for ev in post_event_calendar.scenarios.values() %}
        <td style="color: {% if ev >= 0 %}#38a169{% else %}#c53030{% endif %}; font-weight: bold;">
          ${{ "%.2f" | format(ev) }}
        </td>
        {% endfor %}
      </tr>
    </table>

    <p class="note">
      Short leg settles at intrinsic; P&amp;L is
      independent of short-leg IV path. Long leg valued
      via BSM with {{ "%.0f" | format(
        (1 - 0.97) * 100
      ) }}% IV compression.
    </p>
  </div>
  {% endif %}

  <h2>Strategy Trade Sheets</h2>

  {% for strat in rankings %}
  <div class="trade-sheet">
    <div class="strategy-header">
      <h3 style="margin: 0; font-size: 1.3em;">
        Rank {{ strat.rank }} — {{ strat.name }}
      </h3>
      <span style="opacity: 0.9;">
        Composite Score: {{ "%.4f" | format(strat.score) }}
        {% if strat.risk_penalty_applied %}
          &nbsp;(10% undefined-risk penalty applied)
        {% endif %}
      </span>
    </div>

    {% if strategy_rationale and strat.name in strategy_rationale %}
    <details>
      <summary>Strategy Rationale &amp; Expected Behaviour</summary>
      <div class="rationale-body">{{ strategy_rationale[strat.name] }}</div>
    </details>
    {% endif %}

    <h4>Structure</h4>
    <table>
      <tr>
        <th>Side</th>
        <th>Type</th>
        <th>Strike</th>
        <th>Expiry</th>
        <th>Qty</th>
        <th>Entry $</th>
        <th>IV</th>
        <th>Δ</th>
        <th>Γ</th>
        <th>Vega</th>
      </tr>
      {% for leg in strat.legs %}
      <tr>
        <td><strong>{{ leg.side }}</strong></td>
        <td>{{ leg.option_type | upper }}</td>
        <td>${{ "%.2f" | format(leg.strike) }}</td>
        <td>{{ leg.expiry }}</td>
        <td>{{ leg.qty }}</td>
        <td>{% if leg.entry_price %}${{ "%.2f" | format(leg.entry_price) }}{% else %}—{% endif %}</td>
        <td>{% if leg.iv %}{{ "%.1f" | format(leg.iv * 100) }}%{% else %}—{% endif %}</td>
        <td>{% if leg.delta %}{{ "%.3f" | format(leg.delta) }}{% else %}—{% endif %}</td>
        <td>{% if leg.gamma %}{{ "%.5f" | format(leg.gamma) }}{% else %}—{% endif %}</td>
        <td>{% if leg.vega %}{{ "%.2f" | format(leg.vega) }}{% else %}—{% endif %}</td>
      </tr>
      {% endfor %}
    </table>

    <h4>Net Greeks at Entry</h4>
    <table>
      <tr>
        <th>Net Δ</th>
        <th>Net Γ</th>
        <th>Net Vega</th>
        {% if strat.net_theta is not none %}<th>Net Θ</th>{% endif %}
      </tr>
      <tr>
        <td>{{ "%.4f" | format(strat.net_delta) }}</td>
        <td>{{ "%.6f" | format(strat.net_gamma) }}</td>
        <td>{{ "%.2f" | format(strat.net_vega) }}</td>
        {% if strat.net_theta is not none %}<td>{{ "%.2f" | format(strat.net_theta) }}</td>{% endif %}
      </tr>
    </table>

    <h4>Risk Boundaries</h4>
    <table>
      <tr>
        <th>Max Loss</th>
        <td style="color: #c53030;">${{ "%.2f" | format(strat.max_loss) }}</td>
        <th>Max Gain</th>
        <td style="color: #38a169;">${{ "%.2f" | format(strat.max_gain) }}</td>
      </tr>
      {% if strat.lower_breakeven %}
      <tr>
        <th>Lower BE</th>
        <td>${{ "%.2f" | format(strat.lower_breakeven) }} ({{ "%.2f" | format(strat.lower_be_pct) }}%)</td>
        <th>Upper BE</th>
        <td>
          {% if strat.upper_breakeven %}
            ${{ "%.2f" | format(strat.upper_breakeven) }} ({{ "%.2f" | format(strat.upper_be_pct) }}%)
          {% else %}
            Open
          {% endif %}
        </td>
      </tr>
      {% endif %}
      <tr>
        <th>Capital Required</th>
        <td>${{ "%.2f" | format(strat.capital_required) }}</td>
        <th>Capital Efficiency</th>
        <td>{{ "%.4f" | format(strat.capital_efficiency) }}</td>
      </tr>
    </table>

    <h4>Scenario EV Sensitivity</h4>
    {% if strat.scenario_evs %}
    <table>
      <tr>
        {% for label in strat.scenario_evs.keys() %}
        <th>{{ label | replace('_', ' ') | title }}</th>
        {% endfor %}
      </tr>
      <tr>
        {% for ev in strat.scenario_evs.values() %}
        <td style="color: {% if ev >= 0 %}#38a169{% else %}#c53030{% endif %}; font-weight: bold;">
          ${{ "%.2f" | format(ev) }}
        </td>
        {% endfor %}
      </tr>
    </table>
    {% else %}
    <p class="note">No scenario EVs computed.</p>
    {% endif %}

    <h4>Regime Alignment <span style="font-size: 0.8em; color: #718096;">(Regime: {{ snapshot.regime.composite_regime }}, Confidence: {{ "%.2f" | format(snapshot.regime.confidence) }})</span></h4>
    
    {% if strat.alignment %}
    <table style="text-align: center; width: auto;">
      <tr>
        {% for axis, score in strat.alignment.alignment_heatmap.items() %}
        {% set r = ((1 - score) * 220) | int %}
        {% set g = (score * 200) | int %}
        <td class="heatmap-cell" style="background-color: rgb({{ r }}, {{ g }}, 80); min-width: 100px;">
          <div style="font-size: 0.9em; margin-bottom: 4px;">{{ axis }}</div>
          <div style="font-size: 1.2em;">{{ "%.2f" | format(score) }}</div>
        </td>
        {% endfor %}
      </tr>
    </table>
    
    <div style="margin-top: 12px;">
      <strong>Composite Alignment:</strong> {{ "%.2f" | format(strat.alignment.alignment_score) }}
      &nbsp;|&nbsp;
      <strong>Confidence-Weighted:</strong> {{ "%.2f" | format(strat.alignment.alignment_weighted) }}
    </div>
    {% endif %}
  </div>
  {% endfor %}

  <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #718096; font-size: 0.9em; text-align: center;">
    <p>NVDA Earnings Volatility Analysis Report | Generated by automated regime classification engine</p>
    <p class="note">Regime classification is deterministic and fully auditable. No ML or optimization used.</p>
  </div>

</body>
</html>
"""


def write_report(output_path: Path, context: dict) -> None:
    """Render and write HTML report to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    template = _jinja_env.from_string(HTML_TEMPLATE)
    content = template.render(**context)
    output_path.write_text(content, encoding="utf-8")
