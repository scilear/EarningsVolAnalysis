id: T028
title: Signal graph

objective:
  Implement signal graph with upstream/downstream chain, leader/follower, and signal decay.

context:
  Need to understand signal relationships and dependencies.

inputs:
  - All signals from previous tasks
  - Signal dependency graph

outputs:
  - Signal dependency graph
  - Upstream/downstream chains
  - Leader/follower relationships
  - Signal decay functions

prerequisites:
  - T027

dependencies:
  - T027

non_goals:
  - No live signal generation

requirements:
  - Map all signals to dependency graph
  - Identify upstream/downstream
  - Assign leader/follower roles
  - Implement signal decay

acceptance_criteria:
  - Graph representable
  - Chains traversable
  - Decay functions work

tests:
  unit:
    - test_signal_graph
    - test_upstream_chain
    - test_downstream_chain
    - test_signal_decay
  integration:
    - Full signal traversal

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Decision engine task
  - TODO: ASK FABIEN for signal definitions

failure_modes:
  - Circular dependency → raise error