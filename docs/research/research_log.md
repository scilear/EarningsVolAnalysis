# Research Log

## 2026-04-08

### Observation 1

The existing code already contains the hard parts of a useful prototype:

- event variance extraction
- implied move estimation
- skew and gamma diagnostics
- structure construction
- scenario-based scoring

This argues for refactor-over-rewrite.

### Observation 2

The present data model is too thin for a true event playbook engine. It stores quotes, but not the
event identity or the realized outcome against which candidate structures should be judged.

### Observation 3

Macro should start as a top-level family in the product surface, but the stored event name must be
more specific. `macro` alone is not likely to be a stable research bucket.

### Observation 7

The first storage-friendly macro mapping should keep the family and event slug separate, with a
default proxy and alternates stored alongside it. That allows the engine to keep one canonical
event identity while switching execution underlyings later without a schema rewrite.

### Working Hypothesis

The best first generic families are:

- `earnings`
- `macro`

The best first macro event names are:

- `cpi`
- `payrolls`
- `fomc`

### Observation 9

Schema stability improves when schedule semantics are first-class (`EventSchedule`) rather than
implicit fields on the event object. This keeps pre/post windows consistent across earnings and
macro workloads.

### Observation 10

Keeping event names specific and rejecting family-only labels (`macro`, `earnings`) removes an
early source of bucket ambiguity for historical replay and reporting.

### Observation 5

The event dataset should remain additive to existing quote storage. Instead of rewriting
`option_quotes`, event-level tables can bind event IDs to existing `(ticker, timestamp)` snapshots
and layer derived metrics, realized outcomes, and structure replay PnL on top.

### Observation 6

Outcome comparability requires a dedicated horizon dimension. A shared `horizon_code` (for both
realized outcomes and structure replay exits) avoids drift between "move analysis" and "PnL
analysis" definitions.

The first stable proxy defaults are:

- `cpi` -> `TLT`
- `payrolls` -> `TLT`
- `fomc` -> `SPY`

The proxy record should always keep alternates available:

- `cpi` -> `SPY`
- `payrolls` -> `IWM`, `SPY`
- `fomc` -> `TLT`, `QQQ`

Timestamp caveat:

- date-only macro records are incomplete for intraday research
- FOMC statement time and press conference time should be stored separately when both exist

### Open Questions

- What is the minimum outside-data upgrade needed to move beyond yfinance prototyping?
- Which strategy families deserve first-class support vs dynamic generation?
- Should risk management be encoded as a separate policy engine from structure ranking?

### Decision Update (Task 003)

Risk management is now explicitly modeled as a separate policy/management layer from ranking:

- Ranking remains an ordered candidate list (`ranked_candidates`).
- Policy uses deterministic constraints with explicit stages and actions (`allow/warn/block`).
- Management guidance is structured by trigger/action and does not alter rank computation.
- The contract supports explicit `no_trade_reason` outcomes.

This keeps the first version fully rule-based and audit-friendly.

### Observation 11

The migration test strategy should treat the existing scenario fixtures as the primary confidence
anchor during the refactor. Math-heavy behavior can stay pinned with unit tests, while the event
engine's changing surfaces should be protected with fixture-based contract tests and a small set of
golden examples only after the schema stabilizes.
