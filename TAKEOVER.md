# Event Engine Takeover

This repository started as an NVDA earnings volatility tool. It is now being taken over and
redirected toward a reusable event-based options playbook generator.

## Mission

Turn the repo into a system that can:

1. model scheduled events
2. classify current option-market context
3. rank viable option structures
4. generate practical trade playbooks
5. learn from historical event outcomes

## Current State

- Existing engine: `event_vol_analysis`
- Current strength: analytics and strategy prototyping
- Current weakness: event model, historical replay, and playbook governance

## Working Rules

- Keep major progress in `docs/research/progress_log.md`
- Capture research steps and decisions in `docs/research/research_log.md`
- Break parallelizable work into `tasks/` files with explicit acceptance criteria
- Avoid large destructive renames until compatibility shims or migration notes exist
- Use the project-local virtual environment for Python work:
  - preferred interpreter: `/home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python`
  - do not rely on system `python`

## Phases

### Phase 1. Takeover foundation

- [x] Initial repo assessment completed
- [x] Progress and research tracking created
- [x] Initial task-file backlog created
- [x] Generic event-domain package scaffolded
- [ ] Migration map from `event_vol_analysis` to generic event engine

### Phase 2. Event abstraction

- [ ] Add first-class event schema
- [ ] Separate event-specific loaders from generic analytics
- [ ] Add reusable event context object
- [ ] Add generic playbook output schema

### Phase 3. Historical replay and dataset

- [ ] Extend storage with event metadata and outcomes
- [ ] Add event replay pipeline
- [ ] Add realized move and IV crush measurement
- [ ] Add standardized strategy outcome matrix

### Phase 4. Research workbooks

- [ ] Local event distribution audit
- [ ] Local IV crush surface study
- [ ] Local structure outcome matrix
- [ ] QuantConnect replay modules

## Current Focus

The active section is Phase 1: takeover foundation.

## Notes

The current package remains operationally valuable. The goal is to generalize it in controlled
steps rather than rewrite it blindly.
