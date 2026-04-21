id: T027
title: TYPE 1-5 classifier

objective:
  Implement deterministic TYPE 1-5 rule engine for trade classification.

context:
  TYPE classification combines vol, edge, and positioning into actionable types.

inputs:
  - IV metrics (T023)
  - Edge ratio (T025)
  - Positioning (T026)

outputs:
  - TYPE 1-5 rule engine
  - Classification output
  - Playbook integration

prerequisites:
  - T023, T025, T026

dependencies:
  - T023, T025, T026

non_goals:
  - No ML or learned rules

requirements:
  -TYPE 1: Low IV, RICH, UNDER
  -TYPE 2: Low IV, FAIR, UNDER
  -TYPE 3: Low IV, CHEAP, any positioning
  -TYPE 4: High IV, any edge, any positioning
  -TYPE 5: Extreme case (block trades)
  - Deterministic rules

acceptance_criteria:
  - All 5 types classified
  - Rules deterministic
  - Playbook integration

tests:
  unit:
    - test_type1_classification
    - test_type2_classification
    - test_type3_classification
    - test_type4_classification
    - test_type5_classification
    - test_edge_case_handling
  integration:
    - Full pipeline with TYPE

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Decision engine task
  - TODO: ASK FABIEN for exact rules

failure_modes:
  - Ambiguous conditions → conservative TYPE