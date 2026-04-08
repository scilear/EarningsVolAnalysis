# Task Backlog

These task files are intended for parallel handoff when needed. Each task is scoped so another
agent or contributor can work independently without blocking the main migration.

## Environment Rule

All Python work should use:

- `/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python`

Do not assume `python` on `PATH` is valid for this repo.

## Task Complexity Bands

- `simple`
  Best for a smaller generalist agent. Example: GPT-4.1 class.
- `medium`
  Better for a stronger mid-tier coding/research agent. Example: Kimi K2.5 class.
- `strong`
  Best for frontier coding agents when the task is architecture-sensitive, cross-cutting, or easy
  to get subtly wrong. Example: Codex or Sonnet class.

## Available Tasks

- `001_event_schema_foundation.md`
- `002_event_dataset_and_outcomes.md`
- `003_playbook_policy_engine.md`
- `004_snapshot_bridge.md`
- `005_storage_schema_extension.md`
- `006_event_replay_framework.md`
- `007_earnings_research_workbook.md`
- `008_macro_event_taxonomy_and_mapping.md`
- `009_macro_etf_research_workbook.md`
- `010_quantconnect_replay_scaffold.md`
- `011_output_contract_and_reporting_bridge.md`
- `012_dependency_and_env_cleanup.md`
- `013_test_strategy_for_migration.md`
- `014_task_discovery_followups.md`

## Dependency Summary

- `001` is foundational for `004`, `005`, `008`, and `011`
- `002` feeds `005`, `006`, `007`, `009`, and `010`
- `003` feeds `011`
- `004` should happen before `011`
- `005` should happen before `006`
- `006` should happen before `007`, `009`, and `010`
- `008` should happen before `009`
- `012` and `013` can run early in parallel
- `014` is a meta task that can create new tasks after deeper research

## Recommended Handoff Order

1. `012_dependency_and_env_cleanup.md`
2. `013_test_strategy_for_migration.md`
3. `001_event_schema_foundation.md`
4. `002_event_dataset_and_outcomes.md`
5. `003_playbook_policy_engine.md`
6. `004_snapshot_bridge.md`
7. `005_storage_schema_extension.md`
8. `006_event_replay_framework.md`
9. `008_macro_event_taxonomy_and_mapping.md`
10. `007_earnings_research_workbook.md`
11. `009_macro_etf_research_workbook.md`
12. `010_quantconnect_replay_scaffold.md`
13. `011_output_contract_and_reporting_bridge.md`
14. `014_task_discovery_followups.md`

## Handoff Rule

Only hand off tasks whose acceptance criteria can be verified from changed files, tests, or clear
schema outputs. If a task grows beyond its written scope, split it into a new task file instead of
expanding it informally.
