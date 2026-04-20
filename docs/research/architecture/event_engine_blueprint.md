# Event Engine Blueprint

## Objective

Introduce a generic event-options engine alongside the current `event_vol_analysis` package, then
migrate functionality progressively.

## Target Layers

### 1. Event domain

Owns:

- event family
- event name
- event timestamp
- underlying symbol
- proxy symbol
- timeline semantics

Current schema foundation (Task 001):

- `EventFamily`: top-level family classification
- `EventSpec`: canonical event identity with strict family/name validation
- `EventSchedule`: event date/time plus timeline windows
- `EventWindow`: typed pre-event/event-day/post-event windows with day-offset ranges

### 2. Market context

Owns:

- spot
- term structure
- skew
- GEX
- liquidity
- realized-vol backdrop

### 3. Strategy candidate layer

Owns:

- structure template
- entry timing
- expected edge source
- scenario assumptions
- practical risk notes

### 4. Playbook layer

Owns:

- ranked candidates (strategy output, pre-policy)
- policy constraints (entry/invalidation/no-trade, deterministic)
- recommended structures
- key levels
- management rules
- hedge ideas
- no-trade conditions

### 4b. Policy engine (inside playbook layer, but logically separate)

Owns:

- policy rule registry with stable IDs
- rule stages: `entry`, `invalidation`, `no_trade`
- rule scope: `global` and `structure`
- deterministic evaluation and traceable pass/warn/block outcomes

Hard constraints:

- no learned logic
- no opaque scoring overlays
- no mutation of ranking math

Evaluation sequence:

1. Ranking layer emits ordered candidates.
2. Policy engine evaluates explicit rules against context and candidate risk classification.
3. Playbook emitter outputs:
   - `ranked_candidates` (unaltered ranking view)
   - `recommended` (policy-eligible subset)
   - `policy_constraints` (auditable rule outcomes)
   - optional `no_trade_reason`

### 5. Research / replay layer

Owns:

- event dataset
- replay windows
- realized move metrics
- IV crush metrics
- structure outcome matrix

## Migration Sequence

1. Create a generic package with dataclasses and shared vocabulary
2. Wrap current earnings-specific logic behind generic event interfaces
3. Add event-aware storage and replay data structures
4. Move report generation to a playbook schema
5. Keep `event_vol_analysis` as a compatibility workflow until parity exists

## Non-Goals For The First Slice

- Full package rename
- Immediate deletion of the old pipeline
- Full macro-event implementation before the event schema exists
- Learned policy logic
