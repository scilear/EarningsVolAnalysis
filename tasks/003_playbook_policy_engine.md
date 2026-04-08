# Task 003: Playbook Policy Engine

## Objective

Separate structure ranking from policy gating and management guidance so the engine can emit a
true playbook instead of a score table.

## Scope Ownership

- This task owns policy-engine design and output-contract design only.
- It does not change strategy math, score formulas, or model training.
- It must remain deterministic and rule-based.

## Deliverables

- Policy schema that can represent:
  - entry conditions
  - invalidation conditions
  - no-trade filters
- Management schema that can represent:
  - key levels
  - hedge ideas
  - exit/adjustment guidance
- Output contract that separates:
  - ranked candidates (pre-policy)
  - filtered recommendations (post-policy)
  - explicit no-trade state with traceable rationale

## Proposed Policy Schema (v1, rule-based)

Each policy rule is deterministic and declarative:

- `rule_id`: stable identifier (e.g., `liq_spread_guard`)
- `stage`: `entry | invalidation | no_trade`
- `scope`: `global | structure`
- `condition`: text expression based on observable fields
- `rationale`: plain-language reason
- `action`: `allow | warn | block`

Examples:

- Entry: require spread and open-interest thresholds before order entry.
- Invalidation: if price behavior violates pre-defined event path assumptions, reduce or exit.
- No-trade: block all structures when data quality, liquidity, or regime conflict is too high.

## Proposed Management Schema (v1, rule-based)

Each management item is procedural and tied to market observables:

- `trigger`: condition that activates guidance
- `action`: concrete risk/position action
- `category`: `level | hedge | exit | sizing`
- `notes`: optional context

Examples:

- Key levels around gamma-flip or implied move boundaries.
- Hedge ideas when directionality or convexity assumptions fail.
- Exit adjustments for post-event IV crush or stalled realized movement.

## Proposed Output Contract (v1)

For each event:

- `ranked_candidates`: pure ranking output
- `policy_constraints`: rules evaluated by the policy engine
- `recommended`: candidates that survive policy constraints
- `management_guidance`: post-entry handling instructions
- `no_trade_reason`: nullable explicit stand-aside rationale
- `is_no_trade`: derived boolean

Contract requirements:

- Ranking can be audited independently from policy outcomes.
- Policy decisions are traceable to explicit rules.
- No-trade is first-class, not implied by an empty ranking.

## Acceptance Criteria

- The output clearly separates ranking from policy constraints.
- Each recommended structure can include practical risks and management guidance.
- The engine can express a `no_trade` outcome explicitly.
- The schema is neutral enough to work for both earnings and macro events.
- Rule evaluation is deterministic and auditable (no learned policy logic).

## Notes

Keep the first version rule-based. Do not introduce learned policy logic yet.
