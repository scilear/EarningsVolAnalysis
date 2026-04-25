# Task 048 — Test Infrastructure Fix + Signal Graph Config Expansion

**Priority:** P2
**Status:** pending
**Depends On:** T028
**Estimated Effort:** 2–3 hours

---

## Summary

Two known gaps to address before the cron workflow is trusted in production:

1. **Test infrastructure**: 2 tests fail when run from a directory other than the project root because they use cwd-relative paths. A `conftest.py` setting the project root fixes this.

2. **Signal graph config**: `config/signal_graph_sectors.json` covers ~15 tickers in 3 chains (consumer credit, semis, energy). TYPE 4 classification degrades to "requires manual signal check" for names outside these chains. Expand to cover the full earnings universe.

---

## Problem Statement

### 1. Cwd-relative test failures

Running `pytest` from any directory other than the project root causes 2 failures:

```
FAILED event_vol_analysis/tests/test_signal_graph.py::test_config_loads_without_error
  → FileNotFoundError: config/signal_graph_sectors.json

FAILED event_vol_analysis/tests/test_outcomes.py::test_update_script_runs_and_updates_record
  → No such file or directory: scripts/update_earnings_outcome.py
```

Root cause: `load_signal_graph_config()` uses `"config/signal_graph_sectors.json"` as a relative default; the test subprocess call uses `"scripts/update_earnings_outcome.py"` as a relative path. Both assume the project root as cwd.

### 2. Signal graph coverage gap

Current `config/signal_graph_sectors.json` covers:
- Consumer credit chain: SYF → COF → AXP → V → MA → AMZN
- Semiconductor chain: ASML → LRCX → AMAT → KLAC
- AI/compute chain: NVDA → AMD → INTC → QCOM
- Energy chain: XOM → CVX → COP → SLB

Missing chains relevant to the earnings universe (~50 names):
- Big banks: JPM → BAC → C → WFC → GS → MS
- Mega-cap tech: MSFT → GOOG → META → AAPL
- Retail/consumer: WMT → TGT → COST → HD
- Healthcare/pharma: JNJ → ABT → PFE → MRK
- Cloud/SaaS: AMZN → MSFT → CRM → SNOW

---

## Detailed Deliverables

### 1. `conftest.py` — project root fixture

**File:** `conftest.py` (project root)

```python
import os
import pytest

@pytest.fixture(autouse=True)
def set_project_root(monkeypatch):
    project_root = os.path.dirname(os.path.abspath(__file__))
    monkeypatch.chdir(project_root)
```

This ensures all tests see the project root as cwd regardless of where `pytest` is invoked.

### 2. Signal graph config expansion

**File:** `config/signal_graph_sectors.json`

Add the missing chains to `sector_map` and `factor_map`. Priority order:

1. Big banks (JPM, BAC, C, WFC, GS, MS) — frequently all report in the same week; strong signal chain
2. Mega-cap tech (MSFT, GOOG, META, AAPL) — massive follower effects; MSFT/GOOG report same week
3. Retail (WMT, TGT, COST, HD) — consumer spend chain
4. Healthcare (JNJ, ABT, PFE, MRK) — weaker chain but present
5. Cloud/SaaS — if capacity allows

Minimum viable expansion: banks + mega-cap tech (items 1 + 2). Covers the majority of high-conviction TYPE 4 opportunities.

---

## Acceptance Criteria

- [ ] All 496 tests pass when run via `pytest` from any directory (including `/`)
- [ ] `test_config_loads_without_error` passes consistently
- [ ] `test_update_script_runs_and_updates_record` passes consistently
- [ ] `config/signal_graph_sectors.json` includes at minimum: JPM, BAC, C, WFC, GS, MS, MSFT, GOOG, META, AAPL
- [ ] Signal graph integration test covers at least one bank chain and one tech chain

---

## Testing Strategy

```bash
# Verify tests pass from project root
python -m pytest -q --tb=short

# Verify tests pass from a different directory
cd / && python -m pytest /home/fabien/Documents/EarningsVolAnalysis/ -q --tb=short

# Spot-check signal graph with new chains
python -c "
from event_vol_analysis.analytics.signal_graph import load_signal_graph_config
sm, fm = load_signal_graph_config()
print('Tickers in sector_map:', sorted(sm.keys()))
"
```

---

## References

- **Signal graph module:** `event_vol_analysis/analytics/signal_graph.py`
- **Config file:** `config/signal_graph_sectors.json`
- **Failing tests:** `event_vol_analysis/tests/test_signal_graph.py:163`, `event_vol_analysis/tests/test_outcomes.py:367`
- **T028:** signal graph module spec
