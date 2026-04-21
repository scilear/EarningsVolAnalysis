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
| 016 | Ticker-agnostic audit | Trust blockers | P0 | completed | strong | - |
| 017 | Symmetric butterfly | Structure coverage | P1 | completed | strong | 022 recommended |
| 018 | Capital-normalized ranking | Ranking quality | P1 | completed | medium | 017 recommended |
| 019 | Multi-ticker batch mode | Operator throughput | P1 | completed | strong | 016, 020 |
| 020 | Earnings calendar auto-ingestion | Operator throughput | P1 | completed | medium | - |
| 021 | Fat-tailed move distribution | Modeling quality | P1 | completed | strong | 022 recommended |
| 022 | Regression smoke harness | Trust blockers | P0 | completed | medium | 015 |
| 023 | IV Rank + IV Percentile dual classifier | Playbook alignment | P1 | pending | medium | 022 |
| 024 | Conditional expected move (trimmed mean, 4Q recency, AMC/BMO, conditioning) | Playbook alignment | P1 | pending | strong | 021 |
| 025 | Edge ratio (Implied / Conditional Expected, RICH/FAIR/CHEAP) | Playbook alignment | P1 | pending | medium | 024 |
| 026 | Positioning proxy (OI, P/C, drift, max pain → UNDER/BALANCED/CROWDED) | Playbook alignment | P1 | pending | medium | - |
| 027 | TYPE 1–5 classifier (deterministic rule engine) | Decision engine | P1 | pending | strong | 023, 025, 026 |
| 028 | Signal graph (upstream/downstream chain, leader/follower, signal decay) | Decision engine | P1 | pending | strong | 027 |
| 029 | 4-layer batch report (morning-scan format, --mode playbook-scan) | Decision engine | P1 | pending | medium | 027, 028 |
| 030 | Post-earnings outcome tracking | Calibration | P2 | pending | medium | 002, 027 |
| 031 | Calibration loop (weekly: edge ratio accuracy, TYPE accuracy, no-trade audit) | Calibration | P2 | pending | medium | 030 |
| 032 | Automated earnings season workflow (daily cron + Telegram) | Calibration | P2 | pending | strong | 029, 031 |

## Notes on Current Status

- Task `019` and `020` completed: batch uses auto-discovery (no --event-date required),
  unambiguous dates halt with exit code 2, source limitations documented in USER_GUIDE.
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

1. Close `019` + `020` → batch + auto-ingestion
2. Close `012`, `013`, `014` → tooling hygiene
3. **Playbook alignment layer** (in order):
   - `023` → IV Rank + IV Percentile dual classifier
   - `024` → Conditional expected move (trimmed mean, 4Q recency, AMC/BMO, conditioning)
   - `025` → Edge ratio (Implied / Conditional Expected, RICH/FAIR/CHEAP labeling)
   - `026` → Positioning proxy (OI concentration, P/C ratio, drift vs sector, max pain)
4. **Decision engine**:
   - `027` → TYPE 1–5 classifier (deterministic, rule-based)
   - `028` → Signal graph (upstream/downstream chain, leader/follower, signal decay)
   - `029` → 4-layer batch report (morning-scan format)
5. **Calibration**:
   - `030` → Post-earnings outcome tracking
   - `031` → Calibration loop (weekly review)
   - `032` → Automated earnings season workflow (daily cron + Telegram)

## How to Work This Board

- Read canonical scope in `tasks/<id>_*.md` before coding.
- Keep acceptance criteria verifiable from code/tests/artifacts.
- If scope expands, create a new task file instead of silently broadening the
  existing task.

## Related Docs

- Roadmap: `docs/ROADMAP.md`
- User operations: `docs/USER_GUIDE.md`
- Feature map: `docs/FUNCTIONALITY.md`
