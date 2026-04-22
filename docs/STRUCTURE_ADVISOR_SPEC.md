# Structure Advisor — Generic Option Payoff Query Interface

**Feature:** T039–T041  
**Status:** Draft spec  
**Owner:** Fab (vol-specialist)  
**Priority:** P2 — after T027 TYPE classifier is stable

---

## Problem

The vol-specialist agent currently pulls full option chains into context to price and compare structures. A typical chain response is 200–400 lines across multiple expiries — most of it discarded after extracting 6–8 numbers. This generates unnecessary token cost and puts quantitative analysis (pricing, fitness gating, loss zone calculation) in the agent's reasoning loop rather than in a reproducible tool.

**Desired state:** agent identifies the scenario and payoff intent; tool prices, gates, and compares candidate structures; agent layers narrative judgment on top of a pre-built comparison table.

---

## Design Principle: Two Layers

```
Layer 1 — Agent (narrative)
  Scenario → Payoff type(s) → call tool
  Example: "ceasefire today, long GLD thesis, want crash protection" → payoff=crash

Layer 2 — Tool (quantitative)
  Payoff type + market context → price all candidate structures → rank → return table
  Agent reads the table and adjusts one sentence based on thesis
```

The agent never reads raw chains. The tool never touches narrative.

---

## Payoff Type Taxonomy

Six atomic payoff types. Compound scenarios map to multiple types (agent picks which apply).

| Payoff Type | Description | Canonical scenarios |
|-------------|-------------|---------------------|
| `crash` | Profit from sharp down move (>3% quickly) | Binary event tail risk, macro shock hedge |
| `rally` | Profit from sharp up move | Thesis acceleration, mean reversion after sell-off |
| `sideways` | Profit from no move / range-bound | Post-event vol crush, consolidation, income |
| `vol-expansion` | Profit from IV rising regardless of direction | Pre-event vol buy, uncertain catalyst |
| `vol-compression` | Profit from IV falling | Post-event vol crush, high IV environment |
| `directional-convex` | Profit from move in one direction with convexity | Asymmetric thesis with defined-risk overlay |

**Compound mappings (agent resolves):**

| Scenario | Payoff types |
|----------|-------------|
| Binary event (symmetric) | `crash` + `rally` |
| Binary event (directional thesis) | one of `crash`/`rally` only — agent picks based on thesis |
| Earnings pre-event | `vol-expansion` |
| Earnings post-event (sold vol) | `vol-compression` + `sideways` |
| Long directional thesis with hedge | `directional-convex` + `crash` |

---

## Structure Library (keyed by payoff type)

### `crash`
- Long OTM put (outright)
- Put spread (debit): near-ATM / OTM / far-OTM tiers
- Put ratio backspread (1×2): same-expiry
- Diagonal put backspread (1×2): short near-dated / long far-dated
- Long ATM put (full delta hedge)

### `rally`
- Long OTM call
- Call spread (debit)
- Call ratio backspread

### `sideways`
- Iron condor (short strangle + wing protection)
- Iron butterfly
- Short strangle (naked — requires charter approval flag)
- Calendar spread (sell near / buy far)

### `vol-expansion`
- Long straddle (ATM)
- Long strangle (OTM)
- Back-month calendar (buy far vol, sell near)

### `vol-compression`
- Short straddle / short strangle (flagged as naked short — charter gate)
- Credit put spread
- Credit call spread
- Iron condor (short vol version)

### `directional-convex`
- Debit vertical spread (call or put)
- Risk reversal (sell OTM put / buy OTM call, or reverse)
- 1×2 call backspread
- Covered call (requires existing long position — check portfolio flag)

---

## Query Interface

### CLI (primary usage)

```bash
# Intent-based: price all structures for payoff type
earningsvol query \
  --payoff crash \
  --ticker GLD \
  --expiry 2026-05-15 \
  --spot 429.57

# With budget constraint (filters out structures exceeding budget)
earningsvol query \
  --payoff crash \
  --ticker GLD \
  --expiry 2026-05-15 \
  --spot 429.57 \
  --budget 500

# Structure-specific validation: price and gate a specific structure
earningsvol query \
  --payoff crash \
  --ticker GLD \
  --validate "diagonal:short-May15-420P/long-2x-Jul17-410P"

# Multi-expiry diagonal (agent supplies both legs)
earningsvol query \
  --payoff crash \
  --ticker GLD \
  --short-leg "May15:420P:short:1" \
  --long-leg "Jul17:410P:long:2"
```

### Python API

```python
from event_vol_analysis.structure_advisor import query_structures

result = query_structures(
    payoff_type="crash",
    ticker="GLD",
    expiry="2026-05-15",
    spot=429.57,
    budget=500,
    context={"iv_percentile": 69.2, "dte": 23}
)
# Returns: StructureAdvisorResult with ranked_structures, fitness_flags, vol_regime
```

---

## Output Format

Compact table returned in <60 lines. No raw chain data.

```
Structure Advisor — GLD | payoff: crash | spot: $429.57 | 2026-05-15 (23 DTE)
Vol fitness: IV pctile 69.2% — ELEVATED (long vol expensive; crash protection viable but costly)

RANKED CANDIDATES
─────────────────────────────────────────────────────────────────────────────────────
Rank  Structure              Net debit  Annlzd   Max loss    Breakeven  Loss zone
1     Put spread $420P/$405P  $342       12.5%    $342        $416.6     none
2     Put spread $430P/$410P  $714       26.1%    $714        $422.9     none
3     Long $420P outright     $583       21.3%    $583        $414.2     none (theta decay only)
4     Diagonal 1x2 (May/Jul)  $1,968     19.8%*   $1,968      n/a        $418–$422 (moderate decline)
      * conditional on May expiring OTM — adjusted cost if May assigned: $2,900+

EXCLUDED (budget >$500): [none]
EXCLUDED (fitness gate): Short strangle/straddle — naked short not permitted per charter
EXCLUDED (liquidity): [none at this spot/expiry]

RECOMMENDATION: Rank 1 — put spread $420P/$405P at $342 (12.5% annlzd).
Covers GLD decline from -2.1% to -5.5% from current spot. Defined risk, no loss zone.
Diagonal (Rank 4) is strictly dominated: higher absolute cost AND conditional payoff.
```

**Key fields always present:**
- Net debit (absolute $)
- Annualized carry (%, one-time vs recurring flagged)
- Max loss (= net debit for debit structures)
- Breakeven at expiry
- Loss zone (strikes where loss exceeds debit — applies to ratio/diagonal structures)
- Vol fitness flag (passes/fails for payoff type)
- Explicit exclusion reasons

---

## Fitness Gates (per payoff type)

The tool checks these gates automatically and includes results in output. Does not block output — flags and explains.

| Payoff type | Gate | Check |
|-------------|------|-------|
| `crash` | Long vol not blocked by IV cost | IVP warning if >80% (still prices, flags cost) |
| `rally` | Same as crash | Same |
| `sideways` | No binary event within DTE | Warn if event within DTE window |
| `vol-expansion` | IVP <60 preferred for long vol | Warn if IVP >60 |
| `vol-compression` | No naked short positions | Hard block; suggest credit spread instead |
| `directional-convex` | Portfolio existing position check | Flag if covered call requires existing long not in portfolio |

---

## Integration with Existing Tool

Builds on existing modules — no rewrites.

| Existing module | Role in Structure Advisor |
|----------------|--------------------------|
| `strategies/payoff.py` | Already computes terminal P&L; extend for tabular comparison output |
| `strategies/structures.py` | Structure definitions; add missing structures from deferred backlog |
| `strategies/scoring.py` | EV/CVaR scoring; reuse for ranking but don't require Monte Carlo for simple debit structures |
| `strategies/backspreads.py` | Already handles ratio backspreads; wire into `crash` library |
| `event_vol_analysis/regime.py` | IV percentile + vol regime; pass to fitness gates |

**New module required:** `event_vol_analysis/structure_advisor.py`  
- `query_structures(payoff_type, ticker, expiry, spot, budget, context)` → `StructureAdvisorResult`
- `StructureAdvisorResult.to_table()` → compact string (the output block above)
- `StructureAdvisorResult.ranked_structures` → list of `ScoredStructure`

**Chain data fetching:** use `OptionTrader/tools/option_chain.py` via subprocess; parse only needed strikes (those in candidate structures). Do NOT load full chain into result. Fetch only: bid, ask, mid, IV, delta, vega for the specific strikes used.

---

## Tasks

### T039 — Structure Library + Payoff Type Mapping

**What's needed:**

Register the structure library in `strategies/structures.py` (add missing structures from deferred backlog: diagonal, risk reversal, 1×2 ratio) and create the payoff-type → structure mapping table.

**Deliverable:**
- `PAYOFF_STRUCTURE_MAP: dict[str, list[str]]` — maps each payoff type to list of structure keys
- All 6 payoff types populated with ≥3 candidate structures each
- Missing structures added to `structures.py` (diagonal, risk reversal as minimum)

**Acceptance criteria:**
- `PAYOFF_STRUCTURE_MAP["crash"]` returns ≥4 structure keys
- Each structure key resolves to a valid `Structure` definition
- Smoke tests pass

---

### T040 — Structure Advisor Core (`structure_advisor.py`)

**What's needed:**

New module that takes a payoff-type query, fetches targeted chain data for candidate strikes, prices each structure, runs fitness gates, and returns `StructureAdvisorResult`.

**Deliverable:**
- `query_structures()` function — see Python API above
- Strike targeting: for each candidate structure, compute required strikes from spot + standard offset rules (e.g., OTM put spread = [spot × 0.96, spot × 0.90])
- Fetches only required strikes via `OptionTrader/tools/option_chain.py --strikes A,B,C`
- Annualized carry computation (debit / (spot × DTE / 365))
- Loss zone computation for ratio/diagonal structures
- Fitness gate checks (vol regime, event proximity, naked short filter)
- `StructureAdvisorResult.to_table()` → the compact output block

**Acceptance criteria:**
- Full output in <60 lines
- No raw chain data returned or loaded into caller context
- Diagonal correctly flagged with conditional cost note
- Naked short structures hard-blocked with charter flag

---

### T041 — CLI Integration + Agent Callsite

**What's needed:**

Wire `query_structures` into the `earningsvol` CLI as a `query` subcommand. Update vol-specialist skill documentation to reference this as the canonical option structure query method.

**Deliverable:**
- `earningsvol query [args]` CLI subcommand
- `--output json` flag for programmatic consumption
- Update `agents/vol-specialist/persona.md` DATA TOOLS section: add `earningsvol query` as the canonical way to price option structures

**Acceptance criteria:**
- CLI works with `--payoff crash --ticker GLD --expiry 2026-05-15 --spot 429.57`
- `--validate` flag prices a specific user-supplied structure against the ranked candidates
- Output fits in one terminal page (≤60 lines)

---

## Execution Order

```
T039 (structure library + payoff map)
  ↓
T040 (structure_advisor.py core)
  ↓
T041 (CLI + agent integration)
```

T039 and T040 can overlap once the structure library is stable. T041 is last — depends on T040 producing valid output.

**Dependency on existing work:** T039 depends on `structures.py` having diagonal and risk reversal added. These are in the deferred backlog — pull them forward as part of T039.

---

## What This Does Not Do

- Does not replace the earnings TYPE 1–5 classifier (T027). That is earnings-specific and operates at a different level (event classification vs structure pricing).
- Does not generate trade ideas autonomously. Agent always identifies payoff type; tool prices and compares.
- Does not replace narrative judgment. Agent still decides which payoff types apply to the scenario and whether the recommendation fits the thesis.
- Does not handle portfolio-level hedging (portfolio delta, aggregate notional). That remains the investment-manager / risk layer.
