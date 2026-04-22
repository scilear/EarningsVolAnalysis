# Tasks Index

## Status Legend

| Status | Meaning |
| --- | --- |
| completed | accepted and integrated |
| in_progress | partially complete or active follow-up work |
| pending | not started |

## Task Index

| ID | Task | Priority | Depends On | Status |
| --- | --- | --- | --- | --- |
| T001 | Event schema foundation | P1 | - | completed |
| T002 | Event dataset and outcomes | P1 | T001 | completed |
| T003 | Playbook policy engine | P1 | T001 | completed |
| T004 | Snapshot bridge | P1 | T001 | completed |
| T005 | Storage schema extension | P1 | T001,T002 | completed |
| T006 | Event replay framework | P1 | T002,T005 | completed |
| T007 | Earnings research workbook | P1 | T002,T006 | completed |
| T008 | Macro taxonomy and mapping | P1 | T001 | completed |
| T009 | Macro ETF research workbook | P1 | T006,T008 | completed |
| T010 | QuantConnect replay scaffold | P1 | T002,T006 | completed |
| T011 | Output contract and reporting bridge | P1 | T001,T003,T004 | completed |
| T012 | Dependency and env cleanup | P2 | - | pending |
| T013 | Test strategy for migration | P2 | - | pending |
| T014 | Task discovery follow-ups | P2 | - | pending |
| T015 | Gamma alignment fix | P0 | - | completed |
| T016 | Ticker-agnostic audit | P0 | - | completed |
| T017 | Symmetric butterfly | P1 | T022 | completed |
| T018 | Capital-normalized ranking | P1 | T017 | completed |
| T019 | Multi-ticker batch mode | P1 | T016,T020 | completed |
| T020 | Earnings calendar auto-ingestion | P1 | - | completed |
| T021 | Fat-tailed move distribution | P1 | T022 | completed |
| T022 | Regression smoke harness | P0 | T015 | completed |
| T023 | IV Rank + IV Percentile dual classifier | P1 | T022 | completed |
| T024 | Conditional expected move | P1 | T021 | completed |
| T025 | Edge ratio | P1 | T024 | completed |
| T026 | Positioning proxy | P1 | - | completed |
| T027 | TYPE 1-5 classifier | P1 | T023,T025,T026 | completed |
| T028 | Signal graph | P1 | T027 | completed |
| T029 | 4-layer batch report | P1 | T027,T028 | completed |
| T030 | Post-earnings outcome tracking | P2 | T002,T027 | completed |
| T031 | Calibration loop | P2 | T030 | completed |
| T032 | Automated earnings season workflow | P2 | T029,T031 | completed |
| T039 | Structure library + payoff-type mapping | P2 | T022 | pending |
| T040 | Structure Advisor core (structure_advisor.py) | P2 | T039 | pending |
| T041 | CLI integration + agent skill update | P2 | T040 | pending |

## Dependency Chains

- Foundation: `T001` → `T002` → `T005` → `T006` → (`T007`, `T009`, `T010`)
- Policy/Report: `T001` + `T003` + `T004` → `T011`
- Trust: `T015` → `T022`
- Coverage/Ranking: `T017` → `T018`
- Throughput: `T020` + `T016` → `T019`
- Playbook Alignment: `T022` → `T023` → `T024` → `T025` → `T026` → `T027`
- Decision Engine: `T027` → `T028` → `T029`
- Calibration: `T027` → `T030` → `T031` → `T032`
- Structure Advisor: `T022` → `T039` → `T040` → `T041`

## Detailed Specs

Each task is documented in its own atomic file: `tasks/task_XXX.md`

| ID   | Task File         | Status    |
| ---- | ----------------- | --------- |
| T001 | tasks/task_001.md | completed |
| T002 | tasks/task_002.md | completed |
| T003 | tasks/task_003.md | completed |
| T004 | tasks/task_004.md | completed |
| T005 | tasks/task_005.md | completed |
| T006 | tasks/task_006.md | completed |
| T007 | tasks/task_007.md | completed |
| T008 | tasks/task_008.md | completed |
| T009 | tasks/task_009.md | completed |
| T010 | tasks/task_010.md | completed |
| T011 | tasks/task_011.md | completed |
| T012 | tasks/task_012.md | pending   |
| T013 | tasks/task_013.md | pending   |
| T014 | tasks/task_014.md | pending   |
| T015 | tasks/task_015.md | completed |
| T016 | tasks/task_016.md | completed |
| T017 | tasks/task_017.md | completed |
| T018 | tasks/task_018.md | completed |
| T019 | tasks/task_019.md | completed |
| T020 | tasks/task_020.md | completed |
| T021 | tasks/task_021.md | completed |
| T022 | tasks/task_022.md | completed |
| T023 | tasks/task_023.md | completed |
| T024 | tasks/task_024.md | completed |
| T025 | tasks/task_025.md | completed |
| T026 | tasks/task_026.md | completed |
| T027 | tasks/task_027.md | completed |
| T028 | tasks/task_028.md | completed |
| T029 | tasks/task_029.md | completed |
| T030 | tasks/task_030.md | completed |
| T031 | tasks/task_031.md | completed |
| T032 | tasks/task_032.md | completed |
| T039 | tasks/task_039.md | pending   |
| T040 | tasks/task_040.md | pending   |
| T041 | tasks/task_041.md | pending   |
