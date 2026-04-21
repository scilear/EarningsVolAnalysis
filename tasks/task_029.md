id: T029
title: 4-Layer Batch Report (Morning Scan Format)

objective:
  Add a --mode playbook-scan CLI flag that generates a condensed morning-review
  batch report: one row per name showing all four layers plus TYPE classification,
  designed for a 5-10 minute daily review of a 10-20 name universe.

context:
  The existing batch report is a full deep-dive per ticker. The playbook-scan
  mode replaces that with an operator-facing summary table where TYPE drives the
  visual hierarchy: non-TYPE-5 names are highlighted, TYPE 5 names are present
  but de-emphasized, and every row is expandable to show layer-level reasoning.
  This is the daily interface between the tool and the operator — it must be
  fast to read and unambiguous in its output.

inputs:
  - Batch results from T027 (TypeClassification per ticker)
  - Batch results from T023 (VolRegimeResult per ticker)
  - Batch results from T025 (EdgeRatio per ticker)
  - Batch results from T026 (PositioningResult per ticker)
  - Batch results from T028 (SignalGraphResult per ticker; optional)
  - Earnings calendar with dates

outputs:
  - --mode playbook-scan CLI argument added to main.py
  - PlaybookScanReport: new report format in reports/ directory
  - HTML output with summary table + expandable detail rows
  - Console (terminal) output: condensed text table for quick review
  - Report saved to reports/daily/YYYY-MM-DD_playbook_scan.html

prerequisites:
  - T027 (TYPE classifier — primary output)
  - T028 (signal graph — optional, degrades gracefully if absent)

dependencies:
  - T027
  - T028

non_goals:
  - No automated trade execution
  - No Telegram alerting in this task (that is T032)
  - No change to existing full deep-dive report behavior
  - No real-time refresh (report is generated once at run time)

requirements:
  - CLI:
    - Add --mode {deep-dive|playbook-scan} argument (default: deep-dive for
      backward compat)
    - playbook-scan triggers condensed report generation instead of per-ticker HTML
    - --tickers or --ticker-file still required for input universe
  - Summary table (one row per name):
    - Columns: Ticker | Earnings Date | Vol Regime | Edge Ratio | Positioning |
      Signal (followers) | TYPE | Confidence | Action
    - TYPE column: color-coded in HTML
        1 → green, 2 → yellow, 3 → blue, 4 → orange, 5 → grey (de-emphasized)
    - Sort order: TYPE 1 first, then 2, 3, 4, then 5 last
    - TYPE 5 rows: visually muted (grey text in HTML; bracketed in console)
  - Expandable detail per row (HTML only):
    - Vol Regime: IVR, IVP, buckets, confidence, term structure slope, skew
    - Edge Ratio: implied, conditional expected, ratio, sub-estimates, note
    - Positioning: all 4 individual signals with BULLISH/BEARISH/NEUTRAL labels
    - Signal graph: upstream leaders (with move %), downstream followers (FRESH
      or ABSORBED), tradeable_followers list
    - TYPE rationale: full rationale list from TypeClassification
    - Phase 2 checklist: visible for TYPE 4 names (both sub-types)
  - Console output (terminal):
    - Compact ASCII table, 1 row per name
    - TYPE 5 rows wrapped in [ ] brackets
    - Non-TYPE-5 rows prefixed with >>> to draw attention
    - Phase 2 checklist printed below table for TYPE 4 names
  - Hard filters applied before running analysis (same as playbook universe
    construction rules):
    - Bid-ask spread <15% of mid on near-money options
    - OI >500 on near-money strikes
    - Average daily option volume >1000 contracts
    - Names that fail filters are listed at bottom as "FILTERED OUT: reason"
  - Report file saved to reports/daily/YYYY-MM-DD_playbook_scan.html
    (directory created if it does not exist)
  - Frequency gate check: if >10% of non-filtered names classify as TYPE 1,
    add a banner warning at top of report: "FREQUENCY WARNING: >10% of universe
    is TYPE 1. Cheapness metric may be miscalibrated."

acceptance_criteria:
  - playbook-scan mode produces report without error on a 5-name test universe
  - Summary table rows sorted TYPE 1 → 5
  - TYPE 5 rows de-emphasized in both HTML and console
  - TYPE 4 Phase 2 checklist visible in expanded HTML row and printed in console
  - Hard filter failures listed as FILTERED OUT with reason
  - Frequency warning fires when TYPE 1 rate exceeds 10%
  - Existing --mode deep-dive (default) is unchanged by this task
  - Report saved to reports/daily/ directory

tests:
  unit:
    - test_summary_table_sort_order (TYPE 1 first, TYPE 5 last)
    - test_type5_de_emphasized_html (grey class applied)
    - test_type5_bracketed_console
    - test_non_type5_prefixed_console (>>> prefix)
    - test_phase2_checklist_visible_type4
    - test_phase2_checklist_absent_other_types
    - test_filtered_out_name_listed
    - test_frequency_warning_fires_above_10pct
    - test_frequency_warning_absent_below_10pct
    - test_report_saved_to_daily_dir
  integration:
    - Full playbook-scan run on 10-name universe with at least one TYPE 1,
      one TYPE 4, and several TYPE 5 → HTML report generated, console output
      matches, sort order correct

definition_of_done:
  - --mode playbook-scan CLI flag implemented
  - HTML report with summary table + expandable detail generated
  - Console output: compact ASCII table with TYPE annotations
  - Report saved to reports/daily/ with date in filename
  - All unit and integration tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - The sort order (non-TYPE-5 first) is intentional — it puts actionable names
    at the top. TYPE 5 names still appear (for calibration and no-trade audit),
    just below the actionable section.
  - Do not hide TYPE 5 names. The no-trade audit (T031) requires them to be
    visible and logged.
  - Phase 2 checklists are instructions for manual morning review, not automated
    checks. Make them prominent for TYPE 4 names.
  - The "FILTERED OUT" section at the bottom serves the universe construction
    audit: over time, the operator can see whether filter criteria are too
    aggressive or too loose.

failure_modes:
  - All names filtered out → report shows "All names filtered out" with reasons;
    no summary table
  - T028 signal graph not available → Signal column shows "N/A — signal graph
    not enabled"; TYPE 4 confidence shown as MEDIUM
  - Report directory creation fails → raise IOError with path
  - One name fails analysis mid-batch → log error, continue with remaining names,
    mark failed name as "ANALYSIS ERROR" in table
