id: T025
title: Edge ratio

objective:
  Implement edge ratio (Implied / Conditional Expected) with RICH/FAIR/CHEAP labeling.

context:
  Edge ratio indicates if implied move isrich vs cheap relative to conditional expected.

inputs:
  - Implied move from T024
  - Conditional expected move from T024

outputs:
  - Edge ratio calculation
  - RICH/FAIR/CHEAP classification
  - Playbook integration

prerequisites:
  - T024

dependencies:
  - T024

non_goals:
  - No new structures

requirements:
  - Edge ratio = Implied / Conditional Expected
  - RICH when > threshold (e.g., 1.15)
  - FAIR when within band (e.g., 0.85-1.15)
  - CHEAP when < threshold (e.g., 0.85)

acceptance_criteria:
  - Edge ratio calculated
  - Labeling works
  - Playbook integration

tests:
  unit:
    - test_edge_ratio_calculation
    - test_rich_label
    - test_fair_label
    - test_cheap_label
  integration:
    - Full pipeline with edge ratio

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Playbook alignment task
  - TODO: ASK FABIEN for implementation details

failure_modes:
  - Zero conditional → avoid division by zero