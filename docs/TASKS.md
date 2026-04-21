# Tasks

This is the latest-friendly task board for humans and AI agents.

Detailed task specs remain in `tasks/`. This page is the quick decision and
dependency surface.

## Status Legend

- completed: accepted and integrated
- in_progress: partially complete or active follow-up work
- pending: not started or no confirmed delivery yet

## Active Board

| ID | Task | Track | Priority | Status | Complexity | Depends On |
| --- | --- | --- | --- | --- | --- | --- |
| 001 | Event schema foundation | Core architecture | P1 | completed | strong | - |
| 002 | Event dataset and outcomes | Data model | P1 | completed | strong | 001 |
| 003 | Playbook policy engine | Core architecture | P1 | completed | strong | 001 |
| 004 | Snapshot bridge | Migration | P1 | completed | strong | 001 |
| 005 | Storage schema extension | Data model | P1 | completed | strong | 001, 002 |
| 006 | Event replay framework | Research foundation | P1 | completed | strong | 002, 005 |
| 007 | Earnings research workbook | Research workflow | P1 | completed | medium | 002, 006 |
| 008 | Macro taxonomy and mapping | Research foundation | P1 | completed | medium | 001 |
| 009 | Macro ETF research workbook | Research workflow | P1 | completed | medium | 006, 008 |
| 010 | QuantConnect replay scaffold | Research export | P1 | completed | medium | 002, 006 |
| 011 | Output contract and reporting bridge | Migration | P1 | completed | medium | 001, 003, 004 |
| 012 | Dependency and env cleanup | Tooling hygiene | P2 | pending | simple | - |
| 013 | Test strategy for migration | Quality strategy | P2 | pending | medium | - |
| 014 | Task discovery follow-ups | Backlog process | P2 | pending | simple | - |
| 015 | Gamma alignment fix | Trust blockers | P0 | completed | simple | - |
| 016 | Ticker-agnostic audit | Trust blockers | P0 | in_progress | strong | - |
| 017 | Symmetric butterfly | Structure coverage | P1 | completed | strong | 022 recommended |
| 018 | Capital-normalized ranking | Ranking quality | P1 | completed | medium | 017 recommended |
| 019 | Multi-ticker batch mode | Operator throughput | P1 | in_progress | strong | 016, 020 |
| 020 | Earnings calendar auto-ingestion | Operator throughput | P1 | in_progress | medium | - |
| 021 | Fat-tailed move distribution | Modeling quality | P1 | in_progress | strong | 022 recommended |
| 022 | Regression smoke harness | Trust blockers | P0 | completed | medium | 015 |

## Notes on Current Status

- Task `016` has at least one delivered slice and associated regression tests,
  but remains an audit class task with potential follow-up scope.
- Task `019` has `_run_batch_mode` with ticker loop, summary JSON, partial-failure handling.
  Remaining: integrate auto-ingestion to batch (no event-date supplied path).
- Task `020` has `auto_ingest_earnings_calendar` using yfinance. Test handles exit code 2
  on ambiguous dates. Remaining: document source limitations, surface discovered date.
- Task `021` fully implemented with explicit model selection, calibration, and
  side-by-side comparison. All 18 tests passing.

## Dependency View

- Foundation chain: `001` -> `002` -> `005` -> `006` -> (`007`, `009`, `010`)
- Policy/report chain: `001` + `003` + `004` -> `011`
- Trust chain: `015` -> `022`; `016` before relying on broad batch usage
- Coverage/ranking chain: `017` -> `018`
- Throughput chain: `020` + `016` -> `019`
- Modeling chain: `022` before substantial `021` rollout changes

## Recommended Next Execution Order

1. finish `016` ticker-agnostic audit closure
2. harden `020` event-date ambiguity/staleness behavior
3. harden `019` operator summary output and partial-failure handling
4. deepen `021` calibration + side-by-side comparison surfaces
5. close process/tooling docs for `012`, `013`, `014`

## How to Work This Board

- Read canonical scope in `tasks/<id>_*.md` before coding.
- Keep acceptance criteria verifiable from code/tests/artifacts.
- If scope expands, create a new task file instead of silently broadening the
  existing task.

## Related Docs

- Roadmap: `docs/ROADMAP.md`
- User operations: `docs/USER_GUIDE.md`
- Feature map: `docs/FUNCTIONALITY.md`
