# Implementation Spec v6: Final Delta
## NVDA Earnings Vol Analysis Engine

**Revision:** v5 → v6 (Opus review pass)  
**This document is a DELTA from v5. Read v3 + v4 + v5 + v6 together for the complete picture.**

---

## V5 → V6 CHANGE SUMMARY

| # | Area | v5 | v6 |
|---|------|----|----|
| 1 | Post-event theta test | Tests `build_post_event_calendar` with varying `front_iv` — conflates entry pricing with scenario eval | Reframed: test holds `net_cost` constant, varies IV inputs to `compute_post_event_calendar_scenarios()` directly |
| 2 | Post-event long IV compression | `0.97` hardcoded inline in scenario function | Named constant `POST_EVENT_CALENDAR_LONG_IV_COMPRESSION = 0.97` in `config.py` |
| 3 | Post-event short leg docstring | "collected theta on residually-elevated front IV" (ambiguous — sounds like theta accrues during hold) | Reframed: "sold at IV-inflated premium, settles at intrinsic" |
| 4 | Bug 1 dependency in acceptance criteria | Stated in prose ("fix Bug 1 before shipping") but not encoded in CI | New acceptance criterion: `event_variance_ratio` in `backspread_favorable` must be in [0.50, 1.00] |
| 5 | DTE window constants | `BACKSPREAD_LONG_DTE_MIN/MAX` and `_select_back3_expiry()` use same 21–45 range independently | Data loader references backspread constants directly; single source of truth |

---

## CHANGE 1 — Fix `test_profit_comes_from_theta_not_iv_convergence`

**Problem:** The v5 test description says:

> "call `build_post_event_calendar` with two snapshots differing only in `front_iv`. Scenario EVs must be identical."

This is wrong. `build_post_event_calendar` uses `front_iv` to price the short leg at entry, which changes `net_cost`, which changes scenario EVs. That's correct behavior — entry pricing *should* depend on front IV. The test as written would either fail (correctly functioning code) or require mocking away the entry pricing (testing nothing useful).

**What we actually want to verify:** The scenario evaluation function (`compute_post_event_calendar_scenarios`) does not use short IV in its P&L math. The short leg settles at intrinsic regardless of IV.

**v6 replacement:**

Remove the v5 test `test_profit_comes_from_theta_not_iv_convergence` entirely. Replace with:

```python
def test_scenario_ev_independent_of_short_iv_at_evaluation(self):
    """
    compute_post_event_calendar_scenarios() produces identical EVs
    regardless of what IV the short leg had at entry, because the short
    leg settles at intrinsic.

    Method: call compute_post_event_calendar_scenarios() twice with
    identical (spot, K, t_short, t_long, iv_long, net_cost) — the only
    inputs the function accepts. Since iv_short is not a parameter (v5
    removed it), this test simply confirms the function signature hasn't
    regressed and that two calls with identical inputs produce identical
    outputs (determinism check).

    The real IV-independence guarantee is structural: iv_short is not in
    the function signature (tested by test_iv_short_not_in_scenario_function_signature).
    This test is a belt-and-suspenders determinism check.
    """
    params = dict(
        spot=195.0, K=195.0, t_short=3/365, t_long=25/365,
        iv_long=0.46, net_cost=4.50
    )
    ev_a = compute_post_event_calendar_scenarios(**params)
    ev_b = compute_post_event_calendar_scenarios(**params)
    for scenario in ev_a:
        assert ev_a[scenario] == ev_b[scenario], f"Non-deterministic: {scenario}"
```

**Rationale:** The signature test (`TypeError` on extra arg) is the real guard. This companion test confirms determinism and documents *why* iv_short independence holds (structural, not numerical).

**Updated test count:** No net change (1 replaced, not added).

---

## CHANGE 2 — Post-Event Long IV Compression: Named Constant

**File:** `config.py`

Add:

```python
# Post-event calendar — long leg IV compression at evaluation
POST_EVENT_CALENDAR_LONG_IV_COMPRESSION = 0.97
# Mild compression on back leg after event settlement.
# The back leg (21-45 DTE) retains most of its IV post-event.
# 0.97 = 3% compression, conservative estimate from NVDA historical IV surfaces.
# This is NOT the same as CALENDAR_BACK3_POST_EVENT_IV_FACTOR (0.92),
# which models the larger crush applied at entry pricing for pre-event calendars.
```

**File:** `strategies/post_event_calendar.py`, in `compute_post_event_calendar_scenarios()`

```python
# v5 (inline magic number):
long_val = bsm(spot_T, K, t_remaining, iv_long * 0.97)

# v6 (named constant):
from config import POST_EVENT_CALENDAR_LONG_IV_COMPRESSION
long_val = bsm(spot_T, K, t_remaining, iv_long * POST_EVENT_CALENDAR_LONG_IV_COMPRESSION)
```

**Clarifying comment on the distinction between the two IV factors:**

There are now two IV compression factors that apply to back3 legs in different contexts. To prevent confusion:

```python
# config.py — add this comment block above the post-event calendar section:

# --- IV compression factors: two different contexts ---
# CALENDAR_BACK3_POST_EVENT_IV_FACTOR = 0.92
#   Used in: pre-event calendar scenario evaluation
#   Meaning: how much the back3 IV drops when the event resolves
#   (entry is pre-event, evaluation simulates post-event crush)
#
# POST_EVENT_CALENDAR_LONG_IV_COMPRESSION = 0.97
#   Used in: post-event calendar scenario evaluation
#   Meaning: mild further compression on back3 IV during the holding period
#   (entry is already post-event, IV has already largely normalized)
#
# These are NOT interchangeable. Do not use one where the other belongs.
```

---

## CHANGE 3 — Post-Event Short Leg Docstring: Precision Fix

**File:** `strategies/post_event_calendar.py`, `build_post_event_calendar()` docstring

The v5 handover document (§4.6) describes the short leg as:

> "Short leg: collected theta on residually-elevated front IV (settled at intrinsic)."

This is ambiguous — "collected theta" implies theta accrues during the hold. In reality, the short leg premium is captured at entry (sold at IV-inflated price) and the leg settles at intrinsic at front expiry. There is no ongoing theta "collection" — the P&L is locked in by the difference between sale price and settlement value.

**v6 docstring (replaces v5 version):**

```python
"""
Post-event calendar spread: SELL 1× front ATM call / BUY 1× back3 ATM call.
Entry: 1-3 days after earnings, while front IV is still residually elevated.

Profit model: pure theta spread.
    Short leg: sold at IV-inflated premium pre-settlement. At front expiry,
    settles at intrinsic value. The profit on the short leg is the difference
    between the inflated sale price and intrinsic settlement — this is fully
    determined at entry, not accrued over the holding period.

    Long leg: retains BSM value with mild IV compression
    (iv_long × POST_EVENT_CALENDAR_LONG_IV_COMPRESSION). The cost of the
    long leg is the BSM value erosion over the holding period.

    Net P&L = (short premium - short intrinsic) - (long entry value - long exit value)

This is NOT an IV convergence trade. At the time of entry, IV compression
from the earnings event has already largely occurred. The edge is structural:
the front leg's residual IV elevation creates a premium that exceeds what
theta erosion takes from the back leg over the same period.

Scenarios test stock movement risk, not IV path risk.
"""
```

**Also update handover_opus.md §4.6** (if regenerated) to match this framing. The key sentence change:

```
# Old (v5 handover):
Short leg: collected theta on residually-elevated front IV (settled at intrinsic).

# New (v6):
Short leg: sold at IV-inflated premium, settles at intrinsic at front expiry.
Profit on the short leg = sale price − intrinsic settlement (determined at entry).
```

---

## CHANGE 4 — Bug 1 Dependency: Fail-Loud Acceptance Criterion

**Problem:** The v5 acceptance criteria state in prose that Bug 1 must be fixed before backspreads ship. But none of the 14 acceptance criteria actually *test* this. If Bug 1 is unfixed, `event_variance_ratio` will be >1.0 (typically 20–46×), the `>= 0.50` gate will always pass, and all 14 acceptance criteria will still pass — silently.

**v6: Add acceptance criterion #15**

```
15. In the `backspread_favorable` scenario, `event_variance_ratio` is in [0.50, 1.00].
    Values > 1.00 indicate Bug 1 (event variance 252× inflation) is unfixed.
    This criterion fails if backspreads are passing the entry gate for the
    wrong reason (inflated variance ratio rather than genuine event dominance).
```

**Implementation in test:**

```python
def test_backspread_favorable_event_variance_ratio_sane(self):
    """
    Acceptance criterion #15: event_variance_ratio in backspread_favorable
    scenario must be in [0.50, 1.00].

    If this test fails with ratio >> 1.0, Bug 1 (event_vol.py: annualized
    variance squared instead of 1-day variance) is unfixed. Do not ship
    backspreads until this passes.
    """
    snapshot = generate_scenario("backspread_favorable")
    ratio = snapshot["event_variance_ratio"]
    assert 0.50 <= ratio <= 1.00, (
        f"event_variance_ratio = {ratio:.4f}. "
        f"Expected [0.50, 1.00]. "
        f"If ratio >> 1.0, Bug 1 (252× inflation) is likely unfixed."
    )
```

**Scenario generator implication:** The `backspread_favorable` scenario in `test_data.py` must generate a numerically correct `event_variance_ratio` (not one that relies on the buggy formula). If the scenario generator uses the same buggy `event_vol.py` code path, this test will catch it.

---

## CHANGE 5 — DTE Window Constants: Single Source of Truth

**Problem:** Two independent code paths define the same 21–45 DTE window:

1. `config.py`: `BACKSPREAD_LONG_DTE_MIN = 21`, `BACKSPREAD_LONG_DTE_MAX = 45`
2. `data_loader.py`: `_select_back3_expiry()` hardcodes 21–45 DTE range

If someone changes one and not the other, the data loader could load a back3 chain that the backspread builder rejects (or vice versa).

**v6: Data loader references the config constants**

```python
# data_loader.py

from config import BACKSPREAD_LONG_DTE_MIN, BACKSPREAD_LONG_DTE_MAX

def _select_back3_expiry(available_expiries, back2_expiry, as_of_date):
    """
    Returns first expiry after back2 that falls within the configured
    DTE window for back3 legs.

    DTE bounds from config: BACKSPREAD_LONG_DTE_MIN to BACKSPREAD_LONG_DTE_MAX.
    These are shared with the backspread builder's entry conditions to ensure
    the data loader and strategy builder agree on what qualifies as back3.
    """
    for expiry in sorted(available_expiries):
        if expiry <= back2_expiry:
            continue
        dte = (expiry - as_of_date).days
        if BACKSPREAD_LONG_DTE_MIN <= dte <= BACKSPREAD_LONG_DTE_MAX:
            return expiry
    return None
```

**Rename constants for clarity** (they're no longer backspread-specific — they define back3 selection globally):

```python
# config.py — rename for clarity (back3 is used by calendar AND backspread):

# v5:
BACKSPREAD_LONG_DTE_MIN = 21
BACKSPREAD_LONG_DTE_MAX = 45

# v6:
BACK3_DTE_MIN = 21    # minimum DTE for back3 expiry selection
BACK3_DTE_MAX = 45    # maximum DTE for back3 expiry selection

# Aliases for backward compatibility in backspread code (optional, remove if clean):
BACKSPREAD_LONG_DTE_MIN = BACK3_DTE_MIN
BACKSPREAD_LONG_DTE_MAX = BACK3_DTE_MAX
```

**Update all references:**
- `data_loader.py`: `_select_back3_expiry()` → uses `BACK3_DTE_MIN`, `BACK3_DTE_MAX`
- `strategies/backspreads.py`: entry condition DTE check → uses `BACK3_DTE_MIN`, `BACK3_DTE_MAX` (or the aliases)
- `strategies/calendar.py`: back3 selection → uses `BACK3_DTE_MIN`, `BACK3_DTE_MAX`

Single source of truth. Change once, applies everywhere.

---

## WHAT IS NOT CHANGING (confirmed from v5)

All items listed in v5 "WHAT IS NOT CHANGING" remain unchanged:
- Capital efficiency asymmetry: left as documented
- "Moderate continuation drift" gap: acknowledged, out of scope
- Strategy set freeze: no new strategies until empirical validation

---

## UPDATED CONFIG ADDITIONS (complete list, v6)

Changes from v5 config marked with `# v6`:

```python
# Back3 expiry selection (shared across data loader + all back3 strategies)
BACK3_DTE_MIN = 21                                  # v6: renamed from BACKSPREAD_LONG_DTE_MIN
BACK3_DTE_MAX = 45                                  # v6: renamed from BACKSPREAD_LONG_DTE_MAX

# Calendar
CALENDAR_PREFERRED_BACK = "back3"
CALENDAR_FALLBACK_BACK  = "back1"
CALENDAR_MIN_TERM_SPREAD_DAYS = 14
CALENDAR_BACK3_POST_EVENT_IV_FACTOR = 0.92
CALENDAR_BACK1_POST_EVENT_IV_FACTOR = 0.85

# Backspreads
BACKSPREAD_RATIO = (1, 2)
BACKSPREAD_MAX_DEBIT_FRACTION = 0.15
BACKSPREAD_MIN_WING_WIDTH = 2.5
BACKSPREAD_LONG_DTE_MIN = BACK3_DTE_MIN             # v6: alias
BACKSPREAD_LONG_DTE_MAX = BACK3_DTE_MAX             # v6: alias
BACKSPREAD_POST_EVENT_IV_FACTOR = 0.85
BACKSPREAD_MIN_IV_RATIO = 1.40
BACKSPREAD_MIN_EVENT_VAR_RATIO = 0.50
BACKSPREAD_MAX_IMPLIED_OVER_P75 = 0.90
BACKSPREAD_MIN_SHORT_DELTA = 0.08

# Post-event calendar
POST_EVENT_CALENDAR_ENTRY_MIN_DAYS = 1
POST_EVENT_CALENDAR_ENTRY_MAX_DAYS = 3
POST_EVENT_CALENDAR_MIN_IV_RATIO = 1.10
POST_EVENT_CALENDAR_MIN_SHORT_DTE = 3
POST_EVENT_CALENDAR_LONG_IV_COMPRESSION = 0.97       # v6: was inline magic number
```

---

## FINAL FILE CHANGE MAP (v6 additions to v5 map)

| File | v5 change | v6 addition |
|------|-----------|-------------|
| `config.py` | `BACKSPREAD_MIN_SHORT_DELTA` → `0.08` | Add `POST_EVENT_CALENDAR_LONG_IV_COMPRESSION`; rename DTE constants to `BACK3_DTE_MIN/MAX`; add IV factor disambiguation comment |
| `strategies/post_event_calendar.py` | Removed `iv_short` param; updated docstrings | Replace `0.97` with config constant; rewrite short-leg docstring for precision |
| `data_loader.py` | (no v5 change) | `_select_back3_expiry()` imports `BACK3_DTE_MIN/MAX` from config |
| `strategies/backspreads.py` | (no v5 change) | DTE check references `BACK3_DTE_MIN/MAX` (or aliases) |
| `strategies/calendar.py` | `abs()` on term spread | Back3 selection references `BACK3_DTE_MIN/MAX` |
| `tests/test_post_event_calendar.py` | 2 tests (signature + theta) | Replace theta test with determinism check |
| `tests/test_backspreads.py` | (no v5 change) | Add `test_backspread_favorable_event_variance_ratio_sane` |

---

## FINAL ACCEPTANCE CRITERIA (replaces v5 section)

1. `./run_all_scenarios.sh` runs all 14 scenarios without error
2. `backspread_favorable` → both backspreads in ranked list
3. `backspread_unfavorable`, `backspread_overpriced` → neither backspread appears
4. `post_event_entry` → **only** `POST_EVENT_CALENDAR` in ranked list
5. `post_event_flat` → `POST_EVENT_CALENDAR` absent
6. All pre-earnings scenarios → `POST_EVENT_CALENDAR` absent
7. `should_build_strategy("UNREGISTERED", snapshot)` raises `KeyError`
8. `import structures` with mismatched dicts raises `AssertionError` immediately
9. `compute_post_event_calendar_scenarios(spot, K, t_s, t_l, iv_short, iv_long, net_cost)` raises `TypeError` (wrong arg count — `iv_short` removed)
10. Backspread delta threshold is `0.08` in config and tests
11. Calendar term spread uses `abs()`
12. All tests in all test files pass (29 existing + new)
13. No `float("inf")` or `None` in any strategy dict field used by scoring
14. `POST_EVENT_CALENDAR` alignment == `0.50` in all regime scenarios
15. **`event_variance_ratio` in `backspread_favorable` scenario is in [0.50, 1.00]** — values >1.0 indicate Bug 1 is unfixed; do not ship backspreads until this passes
