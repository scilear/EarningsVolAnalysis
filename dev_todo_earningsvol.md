# EarningsVolAnalysis — Developer Fix List
**Generated:** 2026-02-23  
**Source:** Code review + PM triage (v3 spec)  
**Repo:** scilear/EarningsVolAnalysis

---

## HOW TO USE THIS DOCUMENT

Each task has:
- **File** and **exact location** to edit
- **What is wrong** (root cause)
- **What to write** (exact fix or pattern)
- **Test** to validate it works

Work top to bottom. Do not skip P0 before P1.

---

## P0 — WILL CRASH AT RUNTIME

---

### TASK 1 — Fix `IV_SCENARIOS` config format
**File:** `nvda_earnings_vol/config.py`  
**File:** `nvda_earnings_vol/strategies/payoff.py` (read-only for context)

**Root cause:**  
`config.py` stores `IV_SCENARIOS` as scalar values (strings/floats).  
`payoff.py::_post_iv()` calls `scenario_cfg.get("front")` and `scenario_cfg.get("back")` expecting a dict per scenario.  
Calling `.get()` on a string raises `AttributeError` at runtime.

**Current (broken):**
```python
IV_SCENARIOS: dict = {
    "base_crush": "collapse_to_back",
    "hard_crush": 0.35,
    "expansion": -0.10,
}
```

**Replace with:**
```python
IV_SCENARIOS: dict = {
    "base_crush": {
        "front": "collapse_to_back",
        "back": "unchanged",
    },
    "hard_crush": {
        "front": -0.35,   # front IV crushed 35%
        "back": -0.10,    # back IV mildly compressed 10%
    },
    "expansion": {
        "front": 0.10,    # front IV expands 10%
        "back": 0.05,     # back IV expands 5%
    },
}
```

**Also update `payoff.py::_post_iv()`** to handle the `"unchanged"` back value:
```python
def _post_iv(...) -> float:
    atm_iv = expiry_atm_iv.get(expiry, leg_iv)
    base_atm = front_iv if expiry == front_expiry else back_iv
    scenario_cfg = IV_SCENARIOS.get(scenario)

    if scenario_cfg is None:
        target_atm = base_atm
    else:
        side = "front" if expiry == front_expiry else "back"
        shift = scenario_cfg.get(side)
        if shift == "collapse_to_back":
            target_atm = back_iv
        elif shift == "unchanged" or shift is None:
            target_atm = base_atm
        else:
            target_atm = base_atm * (1 + float(shift))

    if atm_iv <= 0:
        return max(target_atm, TIME_EPSILON)
    return max(leg_iv * (target_atm / atm_iv), TIME_EPSILON)
```

Also add this comment inside `_post_iv()` after the shift is applied, to freeze design intent for future maintainers:
```python
# Skew frozen: IV adjusted via proportional scaling relative to ATM only.
# Post-event RR and BF are assumed unchanged (v3 spec section 4.5).
# Do not add smile-level shift here without a spec change.
return max(leg_iv * (target_atm / atm_iv), TIME_EPSILON)
```

**Test — Part A: Static config structure:**
```python
# In test_strategies.py or a scratch script:
from nvda_earnings_vol.config import IV_SCENARIOS
for name, cfg in IV_SCENARIOS.items():
    assert isinstance(cfg, dict), f"{name} must be a dict"
    assert "front" in cfg and "back" in cfg, f"{name} missing front/back keys"
print("IV_SCENARIOS config OK")
```

**Test — Part B: Dynamic runtime path (REQUIRED — config validity ≠ runtime validity):**
```python
# tests/test_iv_scenarios.py
import datetime as dt
from nvda_earnings_vol.strategies.payoff import _post_iv
from nvda_earnings_vol.config import IV_SCENARIOS

def test_post_iv_runtime_path():
    """Verify _post_iv() executes without error for all scenarios."""
    front_expiry = dt.date(2026, 3, 21)
    back_expiry  = dt.date(2026, 4, 18)

    for scenario in IV_SCENARIOS:
        # Test front leg
        result_front = _post_iv(
            expiry=front_expiry,
            front_expiry=front_expiry,
            back_expiry=back_expiry,
            scenario=scenario,
            front_iv=0.80,
            back_iv=0.50,
            leg_iv=0.82,
            expiry_atm_iv={front_expiry: 0.80},
        )
        assert result_front > 0.0, f"front leg result must be > 0 for scenario {scenario}"

        # Test back leg
        result_back = _post_iv(
            expiry=back_expiry,
            front_expiry=front_expiry,
            back_expiry=back_expiry,
            scenario=scenario,
            front_iv=0.80,
            back_iv=0.50,
            leg_iv=0.51,
            expiry_atm_iv={back_expiry: 0.50},
        )
        assert result_back > 0.0, f"back leg result must be > 0 for scenario {scenario}"

# This test exercises: .get() path, collapse_to_back branch, float shift branch, unchanged branch.
# Without it, the config test passes but the runtime path may still crash.
```

---

## P1 — STRUCTURAL BUGS AFFECTING RANKING OUTPUT

---

### TASK 2 — Fix calendar misclassification in `_is_undefined_risk()`
**File:** `nvda_earnings_vol/strategies/scoring.py`  
**Function:** `_is_undefined_risk()`

**Root cause:**  
Current logic requires `long.expiry == short.expiry` to count a long as covering a short.  
For a calendar (short front call, long back call), expiries differ → long is not counted → short flagged uncovered → calendar = `undefined_risk`.  
Calendars are defined-risk debit structures. This bug applies a 10% score penalty incorrectly and mislabels in the report.

**Current (broken):**
```python
for short in short_calls:
    cover_qty = sum(
        long.qty for long in long_calls
        if long.expiry == short.expiry and long.strike >= short.strike
    )
    if cover_qty < short.qty:
        return True
```

**Replace with:**
```python
def _is_undefined_risk(strategy: Strategy) -> bool:
    """
    A strategy is undefined risk if any short leg is uncovered.
    
    Coverage rules:
    - Short call is covered by a long call at ANY expiry with strike >= short strike.
    - Short put is covered by a long put at ANY expiry with strike <= short strike.
    - Time spreads (calendars, diagonals) are defined-risk: the long back leg
      provides coverage even at a different expiry.
    """
    short_calls = [leg for leg in strategy.legs if leg.option_type == "call" and leg.side == "sell"]
    short_puts  = [leg for leg in strategy.legs if leg.option_type == "put"  and leg.side == "sell"]
    long_calls  = [leg for leg in strategy.legs if leg.option_type == "call" and leg.side == "buy"]
    long_puts   = [leg for leg in strategy.legs if leg.option_type == "put"  and leg.side == "buy"]

    for short in short_calls:
        # Long at ANY expiry with strike >= short strike counts as cover
        cover_qty = sum(
            long.qty for long in long_calls
            if long.strike >= short.strike
        )
        if cover_qty < short.qty:
            return True

    for short in short_puts:
        # Long at ANY expiry with strike <= short strike counts as cover
        cover_qty = sum(
            long.qty for long in long_puts
            if long.strike <= short.strike
        )
        if cover_qty < short.qty:
            return True

    return False
```

**Test:**
```python
# Add to tests/test_scoring.py

import pandas as pd
from nvda_earnings_vol.strategies.structures import OptionLeg, Strategy
from nvda_earnings_vol.strategies.scoring import _is_undefined_risk

front_expiry = pd.Timestamp("2026-03-21")
back_expiry  = pd.Timestamp("2026-04-18")

# Calendar: short front call + long back call at same strike → defined risk
calendar = Strategy("calendar", legs=(
    OptionLeg("call", 800.0, 1, "sell", front_expiry),
    OptionLeg("call", 800.0, 1, "buy",  back_expiry),
))
assert not _is_undefined_risk(calendar), "Calendar must be defined_risk"

# Naked short call → undefined risk
naked = Strategy("naked_call", legs=(
    OptionLeg("call", 800.0, 1, "sell", front_expiry),
))
assert _is_undefined_risk(naked), "Naked call must be undefined_risk"

# Iron condor → defined risk
condor = Strategy("iron_condor", legs=(
    OptionLeg("call", 820.0, 1, "sell", front_expiry),
    OptionLeg("call", 840.0, 1, "buy",  front_expiry),
    OptionLeg("put",  780.0, 1, "sell", front_expiry),
    OptionLeg("put",  760.0, 1, "buy",  front_expiry),
))
assert not _is_undefined_risk(condor), "Iron condor must be defined_risk"

print("_is_undefined_risk tests passed")
```

---

### TASK 3 — Fix robustness metric (use scenario-EV std, not P&L std)
**File:** `nvda_earnings_vol/main.py`  
**Location:** Inside the `for strategy in strategies:` loop

**Root cause:**  
Spec intent: robustness = stability of EV *across IV scenarios and vol shocks*.  
Current code passes `robustness_override = 1 / std(pnls)` which measures P&L variance, not cross-regime stability.  
This systematically favors tight-distribution strategies (condors) over strategies that are stable across market regimes.

**Current (broken):**
```python
robustness = 1.0 / (float(np.std(evs)) + 1e-9)
metrics = compute_metrics(
    strategy, base_pnls, implied_move, hist_p75, spot, robustness
)
```

**Replace with** — robustness is `1 / std(scenario_EVs)`, inverted so LOW std = HIGH robustness score.

**IMPORTANT SCOPE:** `evs` must contain the EV from **every scenario × vol shock combination** — not just the 3 base IV regimes, not just base_crush. The full cross-product of `scenarios × shock_levels` must all be evaluated and appended before computing robustness. Partial aggregation produces a partially-defined robustness metric that will silently mis-rank strategies.

Verify the loop structure evaluates all combinations:
```python
for scenario in scenarios:          # e.g. base_crush, hard_crush, expansion
    for shock in shock_levels:      # e.g. 0, -10, -5, 5, 10
        pnls = strategy_pnl(...)
        evs.append(float(np.mean(pnls)))   # must be len(scenarios) * len(shock_levels) entries
```

Then compute robustness on the full `evs` list:
```python
# evs is the list of EV floats across ALL scenario x shock combinations
scenario_ev_std = float(np.std(evs)) if len(evs) > 1 else 0.0
robustness = 1.0 / (scenario_ev_std + 1e-9)   # low spread across regimes = high robustness

metrics = compute_metrics(
    strategy, base_pnls, implied_move, hist_p75, spot,
    robustness_override=robustness,
)
```

**Important — check normalization direction in `scoring.py::_normalize()`:**  
Higher robustness value should produce higher normalized score. The current `_normalize()` uses min-max with higher = better, which is **correct** because `1 / std` is already inverted (low std → high value → high score). No change needed in `_normalize()` itself.

**Test:**
```python
# Sanity check: a strategy with identical EV across all scenarios
# should score higher robustness than one with variable EV
import numpy as np
stable_evs    = [100.0, 100.0, 100.0, 100.0]
unstable_evs  = [200.0, -50.0, 150.0, 10.0]
robust_stable   = 1.0 / (np.std(stable_evs)   + 1e-9)
robust_unstable = 1.0 / (np.std(unstable_evs) + 1e-9)
assert robust_stable > robust_unstable, "Stable EV must score higher robustness"
print("Robustness direction OK")
```

---

### TASK 4 — Parameterize OTM offset for strangle construction
**File:** `nvda_earnings_vol/config.py`  
**File:** `nvda_earnings_vol/strategies/structures.py`

**Root cause:**  
Strangle OTM offset hardcoded at 5% (`move = spot * 0.05`).  
For NVDA with implied move ~10%, 5% OTM puts both strangle legs *inside* the expected move distribution. This is not a real strangle — it behaves like a wide straddle and inflates its EV and convexity scores unfairly.

**Step 1 — Add to `config.py`:**
```python
# Strangle construction
STRANGLE_OFFSET_PCT: float = 0.05
# NOTE: For production use, calibrate to implied_move.
# Recommended: set to 0.8 * implied_move before running.
# Example: if implied_move = 0.10, set STRANGLE_OFFSET_PCT = 0.08
```

**Step 2 — Update `structures.py::build_strategies()`:**
```python
def build_strategies(
    front_chain: pd.DataFrame,
    back_chain: pd.DataFrame,
    spot: float,
    strangle_offset_pct: float = STRANGLE_OFFSET_PCT,   # add param
) -> list[Strategy]:
    if not (0.0 < strangle_offset_pct < 0.5):
        raise ValueError(
            f"STRANGLE_OFFSET_PCT must be between 0 and 0.5, got {strangle_offset_pct}. "
            "Typical range: 0.05 – 0.15 (tie to implied_move)."
        )
    atm_strike = _nearest_strike(front_chain, spot)
    move = spot * strangle_offset_pct                    # was: spot * 0.05
    otm_call = _nearest_strike(front_chain, spot + move)
    otm_put  = _nearest_strike(front_chain, spot - move)
    wing_call = _nearest_strike(front_chain, otm_call * 1.05)
    wing_put  = _nearest_strike(front_chain, otm_put  * 0.95)
    ...
```

**Step 3 — Pass implied_move into the call in `main.py`:**
```python
# After implied_move is computed:
strangle_offset = implied_move * 0.8   # tie to event distribution
strategies = build_strategies(front_chain, back1_chain, spot, strangle_offset_pct=strangle_offset)
```

**Test:**
```python
# implied_move = 0.10 → offset = 0.08
# strangle strikes must be outside 5% from spot
assert otm_call_strike >= spot * 1.07   # roughly
assert otm_put_strike  <= spot * 0.93
```

---

## P2 — SPEC COMPLIANCE & CODE QUALITY

---

### TASK 5 — Add explicit 0 DTE guard in `main.py`
**File:** `nvda_earnings_vol/main.py`  
**Location:** After `front_expiry` is assigned

**Root cause:**  
If `front_expiry == event_date`, `_time_remaining()` returns `TIME_EPSILON`.  
BSM then prices with near-zero time → near-intrinsic values → silently wrong pre-event vol estimates.  
Should fail loudly, not degrade silently.

**Add immediately after event_date is resolved and before front_expiry assignment:**
```python
# Normalize to date objects — event_date may arrive as pd.Timestamp from yfinance
event_date = event_date.date() if isinstance(event_date, pd.Timestamp) else event_date
```

**Then add the guard after front_expiry is assigned:**
```python
front_expiry = post_event[0]
if front_expiry <= event_date:
    raise ValueError(
        f"Front expiry {front_expiry} must be strictly after event date {event_date}. "
        "Check your event date or option chain data."
    )
```

**Why the type normalization matters:** `pd.Timestamp` vs `datetime.date` comparisons can silently fail or produce incorrect results depending on the Python/pandas version. Normalize first, guard second.

**Test:**
```python
# In test_loader.py or test edge cases:
# Simulate event_date == front_expiry and assert ValueError is raised
import pytest
# (mock the data fetch and assert the guard fires)
```

---

### TASK 6 — Add GEX dealer assumption note to report output
**File:** `nvda_earnings_vol/main.py`  
**Location:** `write_report(...)` call

**Root cause:**  
Spec section 4.6 acceptance criteria: *"assumption note included"* in report.  
Currently only the ambiguity note (`gex_note`) is conditionally added. The baseline dealer-short assumption is never documented in output.

**Add to the `write_report()` data dict:**
```python
write_report(
    report_path,
    {
        ...
        "gex_dealer_note": (
            "GEX sign assumes dealers are net short options. "
            "Interpret regime direction accordingly."
        ),
        "gex_note": gex_note,
        ...
    }
)
```

Then reference `gex_dealer_note` in your Jinja2 HTML template wherever GEX is displayed.

---

### TASK 7 — Align mild/severe diagnostic threshold with spec
**File:** `nvda_earnings_vol/analytics/event_vol.py`  
**Location:** `event_variance()` function

**Root cause:**  
Spec says: `ratio > 10%` → hard warning.  
Code uses: `ratio < 0.25` for mild, ≥ 0.25 for severe.  
This gives a "mild" label to ratios of 10-25% that the spec treats as hard warnings.

**Two options — pick one and document it:**

Option A (align to spec exactly):
```python
if raw_event_var < 0:
    warning_level = "severe" if ratio > 0.10 else "mild"
```

Option B (keep 25% threshold but update spec):
```python
# Intentional deviation from spec: 25% chosen empirically.
# Rationale: 10% threshold too sensitive to microstructure noise in short-DTE options.
# PM decision: update spec section 4.3 to reflect 25% threshold.
if raw_event_var < 0:
    warning_level = "mild" if ratio < 0.25 else "severe"
```

**Pick Option A or get PM sign-off on Option B. Do not leave undocumented.**

---

### TASK 8 — Extract duplicate utilities to `utils.py`
**Files:** `nvda_earnings_vol/analytics/event_vol.py`, `nvda_earnings_vol/main.py`, `nvda_earnings_vol/analytics/skew.py`

**Root cause:**  
`_business_days()` is defined in both `event_vol.py` and `main.py`.  
`_atm_iv()` is defined separately in `event_vol.py` and `skew.py`.  
If ATM selection logic changes, both copies need updating — maintenance risk.

**Step 1 — Create `nvda_earnings_vol/utils.py`:**
```python
"""Shared utility functions."""
from __future__ import annotations
import datetime as dt
import pandas as pd


def business_days(start: dt.date, end: dt.date) -> int:
    """Return number of business days between start and end (exclusive of start)."""
    if end <= start:
        return 0
    return pd.bdate_range(start, end).size - 1


def atm_iv(chain: pd.DataFrame, spot: float) -> float:
    """Return mean IV of the ATM strike in chain."""
    chain = chain.copy()
    chain["distance"] = (chain["strike"] - spot).abs()
    atm_strike = chain.sort_values("distance").iloc[0]["strike"]
    atm = chain[chain["strike"] == atm_strike]
    ivs = atm["impliedVolatility"].dropna()
    if ivs.empty:
        raise ValueError("ATM IV not available.")
    return float(ivs.mean())
```

**Step 2 — Replace local definitions in each file:**
```python
# In event_vol.py, skew.py, main.py — remove local _business_days / _atm_iv
# Replace with:
from nvda_earnings_vol.utils import business_days, atm_iv
```

---

### TASK 9 — Remove dead variable in `_entry_cost()`
**File:** `nvda_earnings_vol/strategies/payoff.py`  
**Function:** `_entry_cost()`

**Root cause:** `key` is computed but never used — `_get_leg_data()` recomputes it internally. Flake8 will flag F841.

**Current:**
```python
for leg in strategy.legs:
    key = (leg.expiry.date(), leg.option_type, float(leg.strike))  # unused
    data = _get_leg_data(lookup, leg)
```

**Fix:**
```python
for leg in strategy.legs:
    data = _get_leg_data(lookup, leg)
```

---

## EDGE CASE TESTS (Spec Section 6)

Add all of the following to `tests/test_event_vol.py`, `tests/test_strategies.py`, `tests/test_scoring.py`:

```python
# 1. Negative event_var
# Provide a front_iv lower than back_iv → raw_event_var < 0
# Assert: event_var clamped to 0, raw_event_var stored, warning_level not None

# 2. Missing second back expiry
# Pass back2_chain=None, back2_expiry=None
# Assert: assumption == "Single-point term structure assumption"

# 3. Zero liquidity after filtering
# Feed chain where all OI < MIN_OI
# Assert: ValueError raised with informative message

# 4. IV = 0 edge case
# Chain with impliedVolatility = 0.0 on ATM strike
# Assert: does not divide by zero, returns TIME_EPSILON or raises cleanly

# 5. No 25d strike found
# Chain with only deep ITM/OTM options
# Assert: skew_metrics returns {"rr25": None, "bf25": None}

# 6. Front expiry = event date (0 DTE)
# Assert: ValueError raised before pricing is attempted

# 7. Undefined-risk strategy detection
# Naked short call → _is_undefined_risk() returns True
# Calendar → _is_undefined_risk() returns False (see Task 2 tests)
# Iron condor → _is_undefined_risk() returns False

# 8. Convexity denominator near zero
# Feed pnls where bottom 10% mean ≈ 0
# Assert: convexity capped at CONVEXITY_CAP, no ZeroDivisionError, log emitted

# 9. Flat term structure — variance subtraction integrity
# Set front_iv == back1_iv == back2_iv (flat vol surface)
# Assert: raw_event_var ≈ 0 (within floating point tolerance ~1e-9)
# This validates that the total variance interpolation does not introduce
# spurious event variance when the term structure is flat.
# Example:
#   front_iv = back1_iv = back2_iv = 0.50
#   Expected: raw_event_var ≈ 0.0
```

---

## FINAL CHECKLIST

| Task | Priority | File(s) | Done |
|------|----------|---------|------|
| 1. Fix IV_SCENARIOS config format + runtime test | P0 | config.py, payoff.py, test_iv_scenarios.py | [ ] |
| 2. Fix calendar undefined_risk misclassification | P1 | scoring.py | [ ] |
| 3. Fix robustness metric (full scenario×shock std) | P1 | main.py | [ ] |
| 4. Parameterize strangle OTM offset + guard | P1 | config.py, structures.py, main.py | [ ] |
| 5. Add 0 DTE explicit guard + type normalization | P2 | main.py | [ ] |
| 6. Add GEX dealer assumption note to report | P2 | main.py, reporter template | [ ] |
| 7. Align mild/severe threshold (or document deviation) | P2 | event_vol.py | [ ] |
| 8. Extract _atm_iv / _business_days to utils.py | P2 | utils.py (new), event_vol.py, skew.py, main.py | [ ] |
| 9. Remove dead `key` variable in _entry_cost | P2 | payoff.py | [ ] |
| 10. Add skew freeze comment in _post_iv() | P2 | payoff.py | [ ] |
| 11. Add all edge case tests (incl. flat term structure) | P2 | tests/ | [ ] |

**Do not mark any P1 item done without running the associated test.**  
**Run `flake8 nvda_earnings_vol/` after all changes.**  
**Run `pytest tests/` before pushing.**
