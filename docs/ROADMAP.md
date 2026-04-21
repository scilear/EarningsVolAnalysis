# Roadmap

This is the latest-only roadmap for EarningsVolAnalysis.

## Vision

Deliver one event-options product with two integrated functions:

- Analyze: pre-event regime and structure ranking for operator decisions.
- Research: post-event dataset, replay analytics, and cross-event learning.

## Current State

Working now:

- Single-name and batch Analyze flows in `event_vol_analysis.main`
- Generic bridge payload emission (`generic_event`, `generic_market_context`,
  `generic_playbook`)
- Event-store backfill, replay context loading, earnings/macro workbooks, and
  QuantConnect scaffold exports

Still weak:

- End-to-end live automation without manual checks
- Full migration away from the legacy analyze runtime
- Production-hardening of QC/LEAN integration

## Now (Trust + Operator Throughput)

Priority objective: preserve trust-critical behavior while improving real
season usability.

Active/high-priority tasks:

- `015` gamma alignment fix (completed)
- `016` ticker-agnostic audit (completed)
- `022` regression smoke harness (completed)
- `019` multi-ticker batch mode (core done; integrate auto-ingestion to close)
- `020` event-date auto-ingestion (implemented; close with source docs)
- `021` fat-tailed move distribution (completed; 18 tests passing)

Exit criteria:

- Alignment and ticker-agnostic behavior stay stable under regression tests.
- Batch runs are resilient to partial ticker failures.
- Event date discovery failures are explicit and actionable.

## Next (Coverage + Ranking Quality)

Priority objective: improve structure menu completeness and ranking quality.

Tasks:

- `017` symmetric butterfly (completed)
- `018` capital-normalized ranking (completed)
- Continue report/operator UX improvements around ranking transparency

Exit criteria:

- Structure set and ranking output remain interpretable and auditable.
- Ranking payload preserves backward compatibility for current consumers.

## Later (Modeling + Automation)

Priority objective: improve simulation realism and reduce manual process burden.

Tasks:

- `021` fat-tailed simulation model (initial capability present; continue
  calibration and comparison surface)
- automated realized-outcome backfill lifecycle
- portfolio/risk policy overlays for deployment constraints

Exit criteria:

- Side-by-side model comparison is available and reproducible.
- Automation additions do not regress trust-critical operator paths.

## Deferred Backlog (Valid, Not Frontline)

- Broken-wing butterfly
- Diagonal spread
- Risk reversal
- Jade lizard
- 1x2 ratio spread
- Skew-dynamics modeling
- Early assignment warning layer
- Portfolio notional limit enforcement

## Execution Rules

- Protect trust path first: run smoke before/after critical changes.
- Keep changes auditable: preserve explicit metrics and deterministic behavior.
- Prefer additive migration: evolve generic layer beside stable operator flow.

## Related Docs

- Task board: `docs/TASKS.md`
- User workflow: `docs/USER_GUIDE.md`
- Feature map: `docs/FUNCTIONALITY.md`
