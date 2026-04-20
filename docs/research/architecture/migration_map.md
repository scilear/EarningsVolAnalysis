# Migration Map

## Goal

Move from `event_vol_analysis` to a generic event engine in additive steps.

## Step 1. Domain vocabulary

New package:

- `event_option_playbook.events`
- `event_option_playbook.context`
- `event_option_playbook.playbook`

Purpose:

- define first-class event objects
- define reusable market-context objects
- define the output contract for a playbook

Status:

- in progress
- Task 001 completed: schema-v1 event foundation (`EventFamily`, `EventWindow`, `EventSchedule`,
  `EventSpec`) with validation and serialization helpers

## Step 2. Compatibility bridge

Add a bridge layer that converts the current `event_vol_analysis` snapshot into:

- `EventSpec`
- `MarketContext`
- `PlaybookCandidate`

Acceptance target:

- the current NVDA report pipeline can emit generic playbook objects without changing strategy
  math yet

## Step 3. Event-aware data model

Extend the current option storage so a snapshot can be tied to:

- event family
- event name
- event timestamp
- relative timing to event
- realized post-event outcomes

Acceptance target:

- one replayable record per event can be reconstructed from stored data

## Step 4. Historical replay

Add an event replay module that evaluates standardized structures and exits over historical events.

Acceptance target:

- the engine can compare implied move, realized move, IV crush, and structure PnL by event family

## Step 5. Replace report-centric output

Move from a ranked HTML report to a playbook recommendation contract that can still render HTML but
is no longer defined by HTML.

Acceptance target:

- reporting becomes a presentation layer, not the product definition

## Step 5a. Policy engine split from ranking (Task 003)

Refine the playbook contract so ranking and policy are explicit, independent surfaces.

Contract direction:

- `ranked_candidates`: pre-policy ranking output
- `policy_constraints`: deterministic entry/invalidation/no-trade rules
- `recommended`: post-policy structures
- `management_guidance`: trigger/action management items
- `no_trade_reason`: explicit stand-aside rationale

Acceptance target:

- policy outcomes are auditable and do not mutate ranking math
- no-trade is explicit and first-class
- schema remains neutral across `earnings` and `macro`

## Immediate Next Coding Step

Build the compatibility bridge from the existing snapshot dictionary in `event_vol_analysis/main.py`
into the new generic domain objects.
