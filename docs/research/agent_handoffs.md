# Agent Handoffs

This file links delegated tasks to active sidecar agent sessions so follow-up instructions or debug
requests can be sent back to the same context when needed.

## Active

| Task | Agent ID | Nickname | Model | Reasoning | Status | Notes |
|---|---|---|---|---|---|---|
| `012_dependency_and_env_cleanup.md` | `019d6df8-89d5-75d1-b2bd-20be4389b43a` | `Chandrasekhar` | `gpt-5.4-mini` | `low` | `running` | Simple environment/dependency documentation task |
| `014_task_discovery_followups.md` | `019d6df8-8a37-7971-9725-3e24805643c8` | `Ramanujan` | `gpt-5.4-mini` | `low` | `running` | Backlog discovery and new task creation task |

## Completed

| Task | Agent ID | Nickname | Status | Notes |
|---|---|---|
| `002_event_dataset_and_outcomes.md` | `019d6e01-670c-7c40-8284-4577d1a597b4` | `Socrates` | `completed` | Additive event/outcome storage design delivered |
| `008_macro_event_taxonomy_and_mapping.md` | `019d6e01-67ea-7670-886a-ea8acbb1bbb7` | `Boole` | `completed` | First stable macro taxonomy and proxy mapping delivered |
| `001_event_schema_foundation.md` | `019d6e01-66b8-7c81-9284-c7f4af8ec9b8` | `Poincare` | `completed` | Schema-v1 foundation delivered and bridge kept compatible |
| `003_playbook_policy_engine.md` | `019d6e01-677b-7e11-a919-75b6d8095b49` | `Halley` | `completed` | Rule-based policy and management contract delivered |
| `013_test_strategy_for_migration.md` | `019d6e06-6810-7390-bb07-b9d7c85b1d68` | `Maxwell` | `completed` | Migration test strategy documented |

## Notes

- These are Codex sidecar agent IDs, which are the closest supported equivalent here to a smaller
  external coding model workflow.
- Reuse the same agent ID for follow-up questions or debugging when possible.
