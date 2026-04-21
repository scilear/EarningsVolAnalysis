id: T003
title: Playbook policy engine

objective:
  Separate structure ranking from policy gating and management guidance so the engine can emit a true playbook.

context:
  Current system outputs score tables. Need policy filtering, management guidance, and explicit no-trade states.

inputs:
  - Ranking output from strategy engine
  - Market context data

outputs:
  - Policy schema (entry/invalidation/no_trade rules)
  - Management schema (levels, hedges, exit guidance)
  - Output contract separating ranked/rcommended/no_trade

prerequisites:
  - T001 completed

dependencies:
  - T001

non_goals:
  - No learned policy logic
  - No strategy math changes
  - No score formula modifications

requirements:
  - Policy rules are deterministic and declarative
  - Management items tied to market observables
  - Output separates pre-policy (ranked) from post-policy (recommended)
  - Explicit no_trade with traceable rationale
  - Schema neutral for earnings and macro events

acceptance_criteria:
  - Output clearly separates ranking from policy constraints
  - Recommended structures include management guidance
  - Engine can express no_trade outcome explicitly
  - Rule evaluation is deterministic

tests:
  unit:
    - test_policy_rule_evaluation
    - test_management_trigger_conditions
    - test_no_trade_rationale
  integration:
    - Full pipeline: ranking → policy → playbook output

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Keep first version rule-based
  - Policy schema v1: rule_id, stage, scope, condition, rationale, action
  - Management schema v1: trigger, action, category, notes

failure_modes:
  - No ranking output → policy engine handles gracefully
  - Conflicting rules → first-match wins, log warning