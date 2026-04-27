# Merged Adversarial Review: DECISION_ORIENTED_WIKI.md

**Reviewers**: Agent (structural review) + External (foundational review)
**Date**: 2026-04-27
**Status**: Confluence of two independent reviews

---

## Summary

Two reviews were conducted in parallel:
1. **Agent Review** — Focused on structural inconsistencies, internal logic failures, and documentation gaps within the document itself
2. **External Review** — Focused on foundational invalidity of the statistical inputs, assumptions, and the economic soundness of the decision model

The two reviews are largely complementary. The structural issues are real but secondary to the foundational ones. The document is internally well-organized but built on statistically weak inputs and unsupported economic assumptions.

---

## TIER 1: FOUNDATIONAL ISSUES (System Breaks Here)

These are the issues that invalidate the decision model regardless of internal consistency.

### F1. Edge Ratio Assumption is Statistically Invalid
**Source**: External review

The system assumes `historical earnings moves → forward distribution`. This is false:

- Earnings moves are non-stationary (guidance regime, macro cycles, management behavior change)
- The system ignores state conditioning (prior trend, positioning, narrative)
- It mixes heterogeneous events (beats, misses, guidance shocks) into one undifferentiated distribution
- With small sample sizes (< 6 observations), the historical distribution is dominated by noise

**Impact**: The primary decision driver (edge ratio) is statistically weak. Everything downstream inherits this weakness.

**Evidence in doc**: Section 4.1, Section 10.B, Section 12 — edge_ratio is positioned as the primary signal with no conditioning or regime adjustment.

---

### F2. Event Variance Extraction is Unstable and Misused
**Source**: Both reviews converge here

- Relies on linear variance interpolation — assumes clean term structure
- front/back IV is polluted by supply/demand (dealer hedging, structured products flows)
- Inverted structures are clamped to 0 — destroying signal rather than handling it correctly
- event_variance_ratio is used as a regime classifier but is highly sensitive to small IV differences
- Breaks exactly when markets are interesting (dislocations, event-week vol crush)

**Internal inconsistency**: Section 3.2 TYPE Classification uses `event_variance_ratio >= 0.50` as a gate within the CHEAP branch, but Section 11 Conflict 4 says inverted structures get clamped to 0 — meaning the gate never fires correctly for inverted structures.

**Impact**: Regime classification (event-dominant vs distributed) is unreliable.

---

### F3. Determinism is Illusion of Robustness
**Source**: External review

The system enforces hard thresholds (0.8 / 1.3), no override logic, strict categorical decisions:

- Creates cliff effects: edge_ratio = 0.79 → LONG_VOL, edge_ratio = 0.81 → NO_TRADE
- Ignores uncertainty bands around all inputs
- Compresses a probabilistic problem into a brittle classifier
- No ranking information retained (a 0.79 and 0.50 edge ratio both produce LONG_VOL with no gradation)

**Agent finding**: The threshold audit table (Section 15) lists thresholds with no provenance check — it claims they come from config.py but this was never verified against actual code.

**Impact**: False precision. The system presents deterministic outputs for inherently uncertain inputs.

---

### F4. Implied Move Calculation Proceeds Despite Wide Spreads
**Source**: Both reviews converge here

The document explicitly states:
> Wide spreads logged but not rejected. Calculation proceeds.

Yet implied_move is the numerator of edge_ratio, which is the primary decision driver.

- Around earnings, ATM spreads are often 2-3x normal
- The slippage formula (`mid - spread * slippage_pct`) does not adjust for spread magnitude
- An implied move derived from wide-spread quotes is not comparable to one from tight quotes

**Internal inconsistency**: Section 10.A hard filter includes `max_spread_pct` threshold, but Section 4.2 says wide spreads are only logged, not rejected. These are contradictory or refer to different things.

**Impact**: edge_ratio becomes unreliable exactly when it matters most (earnings week).

---

### F5. No PnL Model — Optimizing Classification, Not Returns
**Source**: External review + Agent structural finding

- System classifies LONG_VOL / SHORT_VOL / NO_TRADE
- No strategy-level PnL simulation (entry, IV crush timing, early exit, assignment)
- Monte Carlo validates move distribution, not strategy payoff
- No path dependency modeling (IV crush before event, drift, gamma scalping)
- No execution timing sensitivity

**Agent finding**: Section 5 (Financial Interpretation) claims backspreads have "highest priority due to convex payoff" with no supporting evidence. This is a claim, not a finding.

**Impact**: System optimizes for classification accuracy, not economic return.

---

## TIER 2: STRUCTURAL ISSUES (Document Has Internal Failures)

These issues are real but secondary — they compound the foundational problems rather than create new ones.

### S1. TYPE Classification Tree is Internally Inconsistent
**Source**: Agent review

Section 3.2 TYPE Classification tree has a structural error:

```
edge_ratio < 0.8 (CHEAP)?
  ├── event_variance_ratio >= 0.50?
  │   ├── gamma_regime "Amplified Move"?
  │   │   └── TYPE 1 (Long vol convex)
  │   └── TYPE 2 (Long vol directional)   ← UNREACHABLE
  └── edge_ratio >= 1.3 (RICH)?
```

The `event_variance_ratio >= 0.50` check is nested inside the CHEAP branch only. But Section 10.B shows event_variance_ratio as a B-priority signal that applies to both CHEAP and RICH branches.

**Resolution**: TYPE 2 is unreachable via this tree. A correct tree would show event_variance_ratio as a parallel check alongside edge_ratio.

---

### S2. Section 11 Conflict Resolution Has Unenforced Rules
**Source**: Agent review

Conflict 2 states:
> Trust score PASS is required for TYPE 4 (short vol harvest)

But the canonical decision function (Section 12) and decision tree (Section 13) do not implement this check. There is no code in the decision function that gates TYPE 4 on trust_score >= 80.

**Result**: The document specifies a rule in one section and contradicts it in another. Without verification against code, the rule is unenforceable.

---

### S3. Backspread Priority is Asserted, Not Derived
**Source**: Agent review

Section 11 Conflict 3:
> Backspread (if gates pass) — highest priority due to convex payoff

Section 5 Financial Interpretation:
> Precedence: 1. Backspread (highest priority due to convex payoff)

This is stated as fact with no supporting evidence. No performance data, no backtest results, no theoretical derivation in the document.

**Impact**: The ranking system is based on an unsubstantiated claim about backspread superiority.

---

### S4. Liquidity Filter Threshold Proximity
**Source**: Agent review

Section 3.3 uses calibrated thresholds for min_oi and max_spread_pct. Section 15 Threshold Audit lists the same thresholds. But:

- Section 10.A hard filter rejects chains where thresholds fail
- Section 3.3 uses the same thresholds but with PASS/FAIL logic
- Section 4.2 implied move proceeds on wide spreads regardless

This creates a scenario where the same metric triggers a hard filter in one place but not in another, with no explanation of which takes precedence or when.

---

### S5. Gamma Regime is Promoted Beyond Its Informational Role
**Source**: External review + Agent review

Section 10.B classifies gamma_regime as a C-priority secondary modifier. Section 14 Signal Priority Matrix shows it as priority 4. Section 3.2 TYPE Classification uses it to determine TYPE 1 vs TYPE 2 within the CHEAP branch.

- GEX is derived from OI — which is stale and directionless around earnings rolls
- No dealer inventory inference is used
- No dynamic hedging feedback loop exists

Yet it refines TYPE decisions. This is cosmetic signal elevation.

**Agent finding**: Section 10.D (Diagnostic Signals) lists gex_by_strike as informational only. But Section 3.2 uses gamma_regime as a decision input. These are contradictory or refer to different things.

---

### S6. Threshold Audit is Unverified
**Source**: Agent review

Section 15 Threshold Audit lists values and claims locations (config.py, edge_ratio.py) with no verification against actual code.

**Agent observation**: The document was built from code exploration, not from verified config files. Thresholds may differ from what the document claims.

**Missing**: The document does not include a verification step that cross-checks these claimed thresholds against actual config.py values.

---

### S7. Unused Signals List is Incomplete
**Source**: Agent review

Section 15 lists skew_25d, vanna_net, charm_net, macro_vehicle_class, term_structure as unused.

**Likely missing**:
- Historical earnings surprise magnitude
- Options skew dynamics pre-event
- Cross-sectional relative value signals
- Realized vol pre-earnings drift

These are gaps that compound the foundational weakness (F1).

---

## TIER 3: DOCUMENTATION GAPS

### D1. No Evidence of Code Verification
**Source**: Agent review

The document was built from code exploration, not from verified code runs. All thresholds, logic gates, and decision paths are reconstructed, not confirmed.

**Recommendation**: The audit checklist (Section 15) should include a step to verify thresholds against actual config.py before the document is considered authoritative.

---

### D2. Monte Carlo is Disconnected from Strategy
**Source**: External review

Section 4.3 describes Monte Carlo move simulation but:
- It validates implied move reasonableness (market vs historical)
- It does not validate strategy payoff
- It does not connect to backspread or calendar PnL

A reader cannot tell from the document how Monte Carlo output feeds into the decision.

---

### D3. Open Confirmation Mode is Underdocumented
**Source**: Agent review

Use Case 5 (Section 2) mentions open confirmation for detecting overnight changes, but:
- No decision logic for how changes trigger alerts
- No threshold for "material change"
- No integration with the TYPE classification system

This use case appears to be a feature stub with no documented decision model.

---

## PRIORITY MATRIX: What to Fix First

| Issue | Tier | Fix Difficulty | Impact if Fixed |
|-------|------|----------------|-----------------|
| F1: Edge ratio assumption | 1 | Hard (requires re-think) | High |
| F2: Event variance instability | 1 | Medium | High |
| F3: Determinism brittleness | 1 | Medium | High |
| F4: Wide spread handling | 1 | Easy | High |
| F5: No PnL model | 1 | Hard | High |
| S1: TYPE tree inconsistency | 2 | Easy | Medium |
| S2: Unenforced TYPE 4 rule | 2 | Easy | Medium |
| S3: Backspread priority claim | 2 | Medium | Medium |
| S6: Unverified thresholds | 2 | Easy | Medium |
| D1: No code verification | 3 | Easy | Medium |

---

## Honest Bottom Line

The document is well-structured and internally coherent. The architecture is clean. The decision model is deterministic and auditable.

But the system is built on inputs that are statistically weak (edge_ratio on small non-stationary samples), structurally unstable (event variance under term structure distortion), and economically unvalidated (no PnL model, no ranking, no cross-sectional context).

The documentation makes the system look more rigorous than it is. The determinism is real but meaningless if the inputs are wrong.

**The most important fixes are not in the document — they are in the model itself.**

---

*Review version: 2026-04-27*