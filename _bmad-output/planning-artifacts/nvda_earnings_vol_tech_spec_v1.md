Good questions. Here are precise answers.

---

# 1. Calendar Construction

**Use: front-week short / 30–45 DTE long.**

Not next-weekly.

### Why:

* Next-weekly still contains residual event vol contamination.
* 30–45 DTE gives cleaner baseline variance.
* Term structure separation is clearer.
* Vega is more stable.
* Less gamma risk vs short-dated long leg.

Your objective is isolating **event variance mispricing**, not playing weekly decay mechanics.

Implementation rule:

* Short: first expiry after earnings
* Long: first expiry ≥ 30 DTE
* Strike: ATM (closest to spot)

Optional enhancement:
Also test slight OTM (±2%) calendars to reduce gamma shock risk.

---

# 2. Greeks Model

For this project:

**Black–Scholes with market IV is sufficient.**

Do NOT over-engineer with SABR.

Reasons:

* We are not modeling surface evolution.
* We are using observed IV from the chain.
* Skew is already embedded in strike-level IV.
* SABR adds model risk without improving decision quality here.

Important:

* Use forward-adjusted BSM (include dividend yield).
* Use mid IV, not recomputed IV.
* Recalculate delta/gamma/vega from each strike’s own IV.

This keeps internal consistency.

---

# 3. Gamma Exposure (GEX Approximation)

Yes — compute gamma from BSM using each strike’s IV.

That is standard practice.

True dealer positioning is unknowable anyway.

What matters:

[
GEX = \sum (Gamma_i \times OI_i \times 100 \times Spot^2)
]

Use dollar gamma:

[
DollarGamma = Gamma \times OI \times 100 \times Spot
]

Aggregate:

* ±5% around spot
* Whole chain
* By expiry

This gives:

* Net gamma
* Gamma concentration zones
* Approximate flip level

It’s a proxy. That’s acceptable.

What is NOT acceptable:

* Ignoring sign.
* Ignoring expiry segmentation.
* Using total OI without weighting by gamma.

---

# Additional Refinements You Should Add

## A. Vol-of-Vol Sensitivity

Calendars and backspreads are sensitive to IV shift.

Add:

[
\frac{\partial P&L}{\partial IV}
]

Shock:

* ±5 vol points
* ±10 vol points

Report sensitivity.

---

## B. Liquidity Filter

Exclude strikes where:

* Bid/ask spread > 5% of premium
* OI < threshold (e.g., 100 contracts)

Otherwise EV is meaningless.

---

## C. Slippage Model

All structures must be computed with:

* Entry at mid - 10% of spread penalty

Otherwise your EV is overstated.

---

# Final Direction

Then your engine must answer:

* Is upside skew already pricing that?
* Is call wing overpriced?
* Does call backspread dominate straddle on convexity per unit risk?

If upside IV is extremely rich:

Long straddle is inefficient.
Backspread likely superior.
Broken wing fly possibly best risk-adjusted.


