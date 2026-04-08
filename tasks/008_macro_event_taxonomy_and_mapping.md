# Task 008: Macro Event Taxonomy And Mapping

## Objective

Define the first stable macro-event taxonomy and map catalysts to proxy underlyings.

## Complexity

- band: `medium`
- recommended agent: Kimi K2.5 class

## Dependencies

- requires: `001_event_schema_foundation.md`

## Deliverables

- Initial macro event taxonomy
- Mapping proposal for catalyst -> primary ETF proxy
- Notes on timestamp precision and caveats by event type

## Acceptance Criteria

- `macro` remains a top-level family but specific event names are preserved
- The first taxonomy includes at least `cpi`, `payrolls`, and `fomc`
- Proxy selection logic is justified and caveats are explicit
- The result is storage-friendly and does not lock the engine to one ETF

## Research Result

First stable pass:

| family | event name | canonical event key | primary ETF proxy | alternate proxies |
| --- | --- | --- | --- | --- |
| `macro` | `cpi` | `macro.cpi` | `TLT` | `SPY` |
| `macro` | `payrolls` | `macro.payrolls` | `TLT` | `IWM`, `SPY` |
| `macro` | `fomc` | `macro.fomc` | `SPY` | `TLT`, `QQQ` |

Timestamp handling:

- Store the actual release datetime when available, not just the date.
- Persist timezone together with the timestamp, and preserve the source calendar timezone.
- For `fomc`, store the policy statement time and press conference time separately when both exist.
- Treat date-only records as incomplete inputs, not as exact intraday timing.

Proxy selection logic:

- `TLT` is the default duration proxy for inflation and labor prints because those catalysts reprice rates first.
- `SPY` is the default broad-risk proxy for policy meetings because it captures the market-wide repricing path.
- Alternate proxies stay in the record so later research can swap the execution underlyings without changing the event taxonomy.

Research note: [2026-04-08 macro taxonomy and proxy mapping](../docs/research/2026-04-08_macro_event_taxonomy_and_proxy_mapping.md)
