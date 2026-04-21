id: T029
title: 4-layer batch report

objective:
  Implement 4-layer batch report with morning-scan format and --mode playbook-scan.

context:
  Need morning-scan format for batch evaluation.

inputs:
  - T027 TYPE output
  - T028 signal graph
  - Batch mode

outputs:
  - Morning-scan format
  - --mode playbook-scan CLI option
  - 4-layer output (regime, signals, rankings, recommendations)

prerequisites:
  - T027, T028

dependencies:
  - T027, T028

non_goals:
  - No live trading integration

requirements:
  - 4 layer output:
    1. Regime scan
    2. Signal scan
    3. Ranking scan
    4. Recommendation scan
  - Morning-scan format
  - --mode playbook-scan CLI

acceptance_criteria:
  - All 4 layers output
  - Format matches playbook scan
  - CLI works

tests:
  unit:
    - test_layer_1_regime
    - test_layer_2_signals
    - test_layer_3_rankings
    - test_layer_4_recommendations
  integration:
    - Full playbook scan mode

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Decision engine task
  - TODO: ASK FABIEN for format details

failure_modes:
  - Empty layer → output placeholder