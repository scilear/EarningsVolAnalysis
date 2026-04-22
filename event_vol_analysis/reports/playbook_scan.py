"""Playbook scan report generation for morning review batches."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, BaseLoader


# Hard filter thresholds for playbook universe construction
PLAYBOOK_MAX_SPREAD_PCT: float = 0.15  # 15%
PLAYBOOK_MIN_OI: int = 500
PLAYBOOK_MIN_DAILY_VOLUME: int = 1000

TYPE_COLORS: dict[int, str] = {
    1: "#22c55e",  # green
    2: "#eab308",  # yellow
    3: "#3b82f6",  # blue
    4: "#f97316",  # orange
    5: "#9ca3af",  # grey
}


@dataclass
class PlaybookScanRow:
    """One row in the playbook scan summary table."""

    ticker: str
    earnings_date: str
    vol_regime: str
    edge_ratio: str
    positioning: str
    signal: str
    type_: int
    confidence: str
    action: str
    is_type5: bool = False  # Computed property; set to True if type_ is 5
    filter_reason: str | None = None
    error_message: str | None = None
    # Expanded detail fields
    vol_regime_detail: dict[str, Any] = field(default_factory=dict)
    edge_ratio_detail: dict[str, Any] = field(default_factory=dict)
    positioning_detail: dict[str, Any] = field(default_factory=dict)
    signal_detail: dict[str, Any] = field(default_factory=dict)
    type_rationale: list[str] = field(default_factory=list)
    phase2_checklist: list[str] | None = None

    def __post_init__(self) -> None:
        """Auto-compute is_type5 from type_."""
        # is_type5 should always match type_ == 5
        object.__setattr__(self, "is_type5", self.type_ == 5)


@dataclass
class PlaybookScanResult:
    """Complete playbook scan report result."""

    rows: list[PlaybookScanRow]
    filtered_out: list[PlaybookScanRow]
    frequency_warning_fired: bool
    type1_count: int = 0
    type2_count: int = 0
    type3_count: int = 0
    type4_count: int = 0
    type5_count: int = 0
    total_analyzed: int = 0
    total_filtered: int = 0

    def compute_summary(self) -> None:
        """Compute summary statistics from rows."""
        non_filtered = [
            r for r in self.rows if r.filter_reason is None and r.error_message is None
        ]
        self.total_analyzed = len(non_filtered)
        self.total_filtered = len(self.filtered_out)

        for row in non_filtered:
            if row.type_ == 1:
                self.type1_count += 1
            elif row.type_ == 2:
                self.type2_count += 1
            elif row.type_ == 3:
                self.type3_count += 1
            elif row.type_ == 4:
                self.type4_count += 1
            elif row.type_ == 5:
                self.type5_count += 1

        # Frequency check: >10% TYPE 1 triggers warning
        if self.total_analyzed > 0:
            type1_pct = self.type1_count / self.total_analyzed
            self.frequency_warning_fired = type1_pct > 0.10
        else:
            self.frequency_warning_fired = False


def check_playbook_liquidity(
    chain: Any,
    spot: float,
) -> tuple[bool, str | None]:
    """Check if chain passes playbook liquidity filters.

    Returns (passes, reason_if_not).
    """
    if chain is None or (hasattr(chain, "empty") and chain.empty):
        return False, "empty options chain"

    # Check for required columns
    required = {"bid", "ask", "openInterest", "volume"}
    if hasattr(chain, "columns"):
        cols = set(chain.columns)
        missing = required - cols
        if missing:
            return False, f"missing columns: {missing}"
    else:
        return False, "invalid chain format"

    # Filter to near-money (within 10% of spot)
    near_money = chain.copy()
    if "strike" in near_money.columns:
        near_money["dist_pct"] = abs(near_money["strike"] - spot) / spot
        near_money = near_money[near_money["dist_pct"] <= 0.10]

    if near_money.empty:
        return False, "no near-money options"

    # Check bid-ask spread < 15% on near-money
    near_money["spread_pct"] = (near_money["ask"] - near_money["bid"]) / near_money[
        "mid"
    ]
    max_spread = near_money["spread_pct"].max()
    if max_spread >= PLAYBOOK_MAX_SPREAD_PCT:
        return False, f"max spread {max_spread:.1%} >= {PLAYBOOK_MAX_SPREAD_PCT:.1%}"

    # Check OI > 500 on near-money
    if "openInterest" in near_money.columns:
        max_oi = near_money["openInterest"].max()
        if max_oi < PLAYBOOK_MIN_OI:
            return False, f"max OI {max_oi} < {PLAYBOOK_MIN_OI}"

    # Check avg daily volume > 1000
    if "volume" in near_money.columns:
        avg_vol = near_money["volume"].mean()
        if avg_vol < PLAYBOOK_MIN_DAILY_VOLUME:
            return False, f"avg volume {avg_vol:.0f} < {PLAYBOOK_MIN_DAILY_VOLUME}"

    return True, None


def create_scan_row_from_snapshot(
    ticker: str,
    snapshot: dict[str, Any],
) -> PlaybookScanRow:
    """Create a PlaybookScanRow from a full analysis snapshot."""
    vol_regime = snapshot.get("vol_regime", {})
    edge_ratio = snapshot.get("edge_ratio", {})
    positioning = snapshot.get("positioning", {})
    signal_graph = snapshot.get("signal_graph", {})
    type_class = snapshot.get("type_classification", {})

    vol_label = "N/A"
    if vol_regime:
        vol_label = vol_regime.get("vol_regime", "N/A")
        if vol_label is None:
            vol_label = "N/A"

    edge_label = edge_ratio.get("label", "N/A") if edge_ratio else "N/A"
    edge_conf = edge_ratio.get("confidence", "N/A") if edge_ratio else "N/A"

    pos_label = positioning.get("label", "N/A") if positioning else "N/A"

    # Signal column - leaders/followers
    signal_val = "N/A"
    if signal_graph:
        followers = signal_graph.get("tradeable_followers", [])
        absorbed = signal_graph.get("absorbed_followers", [])
        if followers:
            signal_val = f"Followers: {', '.join(followers)}"
        elif absorbed:
            signal_val = f"Absorbed: {', '.join(absorbed)}"
        else:
            signal_val = "No signal"

    type_val = type_class.get("type", 5) if type_class else 5
    conf = type_class.get("confidence", "LOW") if type_class else "LOW"
    action = type_class.get("action_guidance", "No trade") if type_class else "No trade"
    rationale = type_class.get("rationale", []) if type_class else []
    phase2 = type_class.get("phase2_checklist") if type_class else None

    return PlaybookScanRow(
        ticker=ticker,
        earnings_date=str(snapshot.get("event_date", "N/A")),
        vol_regime=vol_label,
        edge_ratio=f"{edge_label} ({edge_conf})",
        positioning=pos_label,
        signal=signal_val,
        type_=type_val,
        confidence=conf,
        action=action,
        vol_regime_detail=vol_regime,
        edge_ratio_detail=edge_ratio,
        positioning_detail=positioning,
        signal_detail=signal_graph,
        type_rationale=rationale,
        phase2_checklist=phase2,
    )


def sort_playbook_rows(rows: list[PlaybookScanRow]) -> list[PlaybookScanRow]:
    """Sort rows by TYPE: 1,2,3,4,5 (non-TYPE5 first, TYPE5 last)."""
    return sorted(
        rows,
        key=lambda r: (r.is_type5, r.type_),
    )


# Jinja2 environment for playbook scan template
_playbook_env = Environment(loader=BaseLoader())

PLAYBOOK_SCAN_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Playbook Scan - {{ scan_date }}</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 20px;
      color: #1b1b1b;
      background: #f5f5f5;
    }
    h1 {
      color: #16334c;
      border-bottom: 3px solid #16334c;
      padding-bottom: 12px;
    }
    h2 {
      color: #16334c;
      margin-top: 28px;
      border-bottom: 1px solid #ddd;
      padding-bottom: 8px;
    }
    .frequency-warning {
      background: #fef3c7;
      border: 2px solid #f59e0b;
      border-radius: 8px;
      padding: 16px;
      margin: 16px 0;
      font-weight: bold;
      color: #92400e;
    }
    .frequency-warning::before {
      content: "⚠ ";
    }
    table {
      border-collapse: collapse;
      width: 100%;
      margin: 16px 0;
      font-size: 0.9em;
      background: white;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    th, td {
      border: 1px solid #d1d5db;
      padding: 10px 12px;
      text-align: left;
    }
    th {
      background-color: #1f2937;
      color: white;
      font-weight: 600;
    }
    tr.type5-row {
      background: #f3f4f6;
      color: #9ca3af;
    }
    tr.type5-row td {
      color: #9ca3af;
    }
    tr:not(.type5-row):hover {
      background: #f9fafb;
    }
    .type-1 { color: #22c55e; font-weight: bold; }
    .type-2 { color: #eab308; font-weight: bold; }
    .type-3 { color: #3b82f6; font-weight: bold; }
    .type-4 { color: #f97316; font-weight: bold; }
    .type-5 { color: #9ca3af; }
    details {
      margin: 8px 0;
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
    }
    summary {
      cursor: pointer;
      padding: 12px 16px;
      font-weight: 600;
      color: #374151;
      background: #f9fafb;
      border-radius: 6px;
      user-select: none;
    }
    summary:hover {
      background: #f3f4f6;
    }
    .detail-body {
      padding: 16px;
      border-top: 1px solid #e5e7eb;
    }
    .detail-section {
      margin-bottom: 16px;
    }
    .detail-section h4 {
      margin: 12px 0 8px;
      color: #4b5563;
      font-size: 0.9em;
      text-transform: uppercase;
    }
    .detail-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      font-size: 0.85em;
    }
    .detail-item {
      padding: 4px 8px;
      background: #f9fafb;
      border-radius: 4px;
    }
    .detail-label {
      color: #6b7280;
      font-size: 0.85em;
    }
    .checklist {
      background: #fffbeb;
      border: 1px solid #fed7aa;
      border-radius: 4px;
      padding: 12px;
      margin-top: 8px;
    }
    .checklist li {
      margin: 4px 0;
      color: #9a3412;
      font-size: 0.9em;
    }
    .filtered-out {
      background: #fef2f2;
      border-left: 4px solid #ef4444;
      padding: 12px 16px;
      margin: 8px 0;
    }
    .filtered-out strong {
      color: #dc2626;
    }
    .summary-stats {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 12px;
      margin: 16px 0;
    }
    .stat-box {
      background: white;
      padding: 16px;
      border-radius: 8px;
      text-align: center;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .stat-value {
      font-size: 1.5em;
      font-weight: bold;
      color: #1f2937;
    }
    .stat-label {
      font-size: 0.8em;
      color: #6b7280;
      text-transform: uppercase;
    }
    .type-1-stat .stat-value { color: #22c55e; }
    .type-2-stat .stat-value { color: #eab308; }
    .type-3-stat .stat-value { color: #3b82f6; }
    .type-4-stat .stat-value { color: #f97316; }
    .type-5-stat .stat-value { color: #9ca3af; }
    .footer {
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid #e5e7eb;
      color: #9ca3af;
      font-size: 0.85em;
      text-align: center;
    }
  </style>
</head>
<body>
  <h1>Playbook Scan - {{ scan_date }}</h1>

  {% if frequency_warning %}
  <div class="frequency-warning">
    FREQUENCY WARNING: >10% of universe is TYPE 1. Cheapness metric may be miscalibrated.
  </div>
  {% endif %}

  <h2>Summary Statistics</h2>
  <div class="summary-stats">
    <div class="stat-box type-1-stat">
      <div class="stat-value">{{ type1_count }}</div>
      <div class="stat-label">TYPE 1</div>
    </div>
    <div class="stat-box type-2-stat">
      <div class="stat-value">{{ type2_count }}</div>
      <div class="stat-label">TYPE 2</div>
    </div>
    <div class="stat-box type-3-stat">
      <div class="stat-value">{{ type3_count }}</div>
      <div class="stat-label">TYPE 3</div>
    </div>
    <div class="stat-box type-4-stat">
      <div class="stat-value">{{ type4_count }}</div>
      <div class="stat-label">TYPE 4</div>
    </div>
    <div class="stat-box type-5-stat">
      <div class="stat-value">{{ type5_count }}</div>
      <div class="stat-label">TYPE 5</div>
    </div>
  </div>

  <p style="color: #6b7280; font-size: 0.9em;">
    Analyzed: {{ total_analyzed }} names |
    Filtered: {{ total_filtered }} names
  </p>

  <h2>Summary Table</h2>
  <table>
    <thead>
      <tr>
        <th>Ticker</th>
        <th>Earnings Date</th>
        <th>Vol Regime</th>
        <th>Edge Ratio</th>
        <th>Positioning</th>
        <th>Signal</th>
        <th>TYPE</th>
        <th>Confidence</th>
        <th>Action</th>
      </tr>
    </thead>
    <tbody>
      {% for row in rows %}
      <tr class="{% if row.is_type5 %}type5-row{% endif %}">
        <td><details><summary>{{ row.ticker }}</summary>
          <div class="detail-body">
            {% if row.vol_regime_detail %}
            <div class="detail-section">
              <h4>Vol Regime Details</h4>
              <div class="detail-grid">
                <div class="detail-item"><span class="detail-label">IVR:</span> {{ row.vol_regime_detail.get('ivr', 'N/A') }}</div>
                <div class="detail-item"><span class="detail-label">IVP:</span> {{ row.vol_regime_detail.get('ivp', 'N/A') }}</div>
                <div class="detail-item"><span class="detail-label">Confidence:</span> {{ row.vol_regime_detail.get('vol_confidence_label', 'N/A') }}</div>
                <div class="detail-item"><span class="detail-label">Term:</span> {{ row.vol_regime_detail.get('term_structure_regime', 'N/A') }}</div>
              </div>
            </div>
            {% endif %}

            {% if row.edge_ratio_detail %}
            <div class="detail-section">
              <h4>Edge Ratio Details</h4>
              <div class="detail-grid">
                <div class="detail-item"><span class="detail-label">Implied:</span> {{ "%.2f%%" | format(row.edge_ratio_detail.get('implied', 0) * 100) }}</div>
                <div class="detail-item"><span class="detail-label">Conditional:</span> {{ "%.2f%%" | format(row.edge_ratio_detail.get('conditional_expected_primary', 0) * 100) }}</div>
                <div class="detail-item"><span class="detail-label">Ratio:</span> {{ "%.3f" | format(row.edge_ratio_detail.get('ratio', 0)) }}</div>
                <div class="detail-item"><span class="detail-label">Label:</span> {{ row.edge_ratio_detail.get('label', 'N/A') }}</div>
                <div class="detail-item" style="grid-column: span 2;"><span class="detail-label">Note:</span> {{ row.edge_ratio_detail.get('note', '') }}</div>
              </div>
            </div>
            {% endif %}

            {% if row.positioning_detail %}
            <div class="detail-section">
              <h4>Positioning Details</h4>
              <div class="detail-grid">
                <div class="detail-item"><span class="detail-label">Label:</span> {{ row.positioning_detail.get('label', 'N/A') }}</div>
                <div class="detail-item"><span class="detail-label">Direction:</span> {{ row.positioning_detail.get('direction', 'N/A') or 'N/A' }}</div>
                <div class="detail-item"><span class="detail-label">Confidence:</span> {{ row.positioning_detail.get('confidence', 'N/A') }}</div>
                <div class="detail-item"><span class="detail-label">Available:</span> {{ row.positioning_detail.get('available_count', 0) }}/4</div>
              </div>
            </div>
            {% endif %}

            {% if row.signal_detail and row.signal_detail.get('nodes') %}
            <div class="detail-section">
              <h4>Signal Graph</h4>
              <div class="detail-grid">
                <div class="detail-item" style="grid-column: span 2;"><span class="detail-label">Tradeable Followers:</span> {{ row.signal_detail.get('tradeable_followers', []) | join(', ') or 'none' }}</div>
                <div class="detail-item" style="grid-column: span 2;"><span class="detail-label">Absorbed Followers:</span> {{ row.signal_detail.get('absorbed_followers', []) | join(', ') or 'none' }}</div>
              </div>
            </div>
            {% endif %}

            {% if row.type_rationale %}
            <div class="detail-section">
              <h4>TYPE Rationale</h4>
              <ul style="font-size: 0.85em; color: #4b5563;">
                {% for item in row.type_rationale %}
                <li>{{ item }}</li>
                {% endfor %}
              </ul>
            </div>
            {% endif %}

            {% if row.phase2_checklist %}
            <div class="detail-section">
              <h4>Phase 2 Checklist</h4>
              <ul class="checklist">
                {% for item in row.phase2_checklist %}
                <li>{{ item }}</li>
                {% endfor %}
              </ul>
            </div>
            {% endif %}
          </div>
        </details></td>
        <td>{{ row.earnings_date }}</td>
        <td>{{ row.vol_regime }}</td>
        <td>{{ row.edge_ratio }}</td>
        <td>{{ row.positioning }}</td>
        <td>{{ row.signal }}</td>
        <td class="type-{{ row.type_ }}">{{ row.type_ }}</td>
        <td>{{ row.confidence }}</td>
        <td>{{ row.action }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  {% if filtered_out %}
  <h2>Filtered Out</h2>
  {% for row in filtered_out %}
  <div class="filtered-out">
    <strong>{{ row.ticker }}</strong>: {{ row.filter_reason or row.error_message or 'unknown reason' }}
  </div>
  {% endfor %}
  {% endif %}

  <div class="footer">
    <p>Generated: {{ scan_timestamp }} | Playbook Scan Mode</p>
  </div>
</body>
</html>
"""


def render_playbook_scan_html(
    result: PlaybookScanResult,
    scan_date: str,
) -> str:
    """Render playbook scan HTML report."""
    template = _playbook_env.from_string(PLAYBOOK_SCAN_HTML_TEMPLATE)
    now = dt.datetime.now().isoformat()
    context = {
        "scan_date": scan_date,
        "scan_timestamp": now,
        "rows": result.rows,
        "filtered_out": result.filtered_out,
        "type1_count": result.type1_count,
        "type2_count": result.type2_count,
        "type3_count": result.type3_count,
        "type4_count": result.type4_count,
        "type5_count": result.type5_count,
        "total_analyzed": result.total_analyzed,
        "total_filtered": result.total_filtered,
        "frequency_warning": result.frequency_warning_fired,
    }
    return template.render(**context)


def format_console_table(rows: list[PlaybookScanRow]) -> str:
    """Format playbook scan as compact ASCII table for console."""
    lines: list[str] = []
    header = (
        f"{'Ticker':<8} {'Earnings':<12} {'Vol Reg':<12} "
        f"{'Edge':<14} {'Position':<12} {'Signal':<20} "
        f"{'TYPE':<6} {'Conf':<8} {'Action'}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for row in rows:
        prefix = ">>>" if not row.is_type5 else "[ ]"
        action_short = row.action[:30] if len(row.action) > 30 else row.action
        line = (
            f"{prefix} {row.ticker:<6} {row.earnings_date:<12} {row.vol_regime:<12} "
            f"{row.edge_ratio:<14} {row.positioning:<12} {row.signal:<20} "
            f"{row.type_:<6} {row.confidence:<8} {action_short}"
        )
        lines.append(line)

        # Print phase 2 checklist for TYPE 4
        if row.type_ == 4 and row.phase2_checklist:
            for item in row.phase2_checklist:
                lines.append(f"    └ {item}")

    return "\n".join(lines)


def save_playbook_scan_report(
    result: PlaybookScanResult,
    output_dir: Path | None = None,
) -> Path:
    """Save playbook scan report to daily directory.

    Returns the path to the saved report.
    """
    if output_dir is None:
        output_dir = Path("reports/daily")
    output_dir.mkdir(parents=True, exist_ok=True)

    today = dt.date.today().isoformat()
    filename = f"{today}_playbook_scan.html"
    output_path = output_dir / filename

    html_content = render_playbook_scan_html(result, today)
    output_path.write_text(html_content, encoding="utf-8")

    return output_path
