---
title: Macro Event Taxonomy And Proxy Mapping
date: 2026-04-08
task: "008"
status: stable-first-pass
---

# Macro Event Taxonomy And Proxy Mapping

This note captures the first stable macro-event taxonomy for the event engine. It keeps
`macro` as the top-level family, preserves specific event slugs, and stores a default proxy
plus alternates so the engine is not hard-wired to one ETF.

## Canonical Taxonomy

| family | event name | canonical event key | primary ETF proxy | alternate proxies |
| --- | --- | --- | --- | --- |
| `macro` | `cpi` | `macro.cpi` | `TLT` | `SPY` |
| `macro` | `payrolls` | `macro.payrolls` | `TLT` | `IWM`, `SPY` |
| `macro` | `fomc` | `macro.fomc` | `SPY` | `TLT`, `QQQ` |

## Mapping Rationale

- `CPI` is first-order duration news, so `TLT` is the default proxy.
- `payrolls` is also a rates-sensitive labor print, so `TLT` stays the default proxy.
- `FOMC` is the broadest policy repricing event in this first pass, so `SPY` is the default
  execution proxy, with `TLT` retained as the companion duration view.

## Storage Rules

- Store the family and event name separately instead of collapsing to a single `macro` bucket.
- Persist `canonical event key`, `primary ETF proxy`, and `alternate proxies` as distinct fields.
- Keep the mapping additive so later research can change the proxy list without changing the
  event identity.

## Timestamp Caveats

- Store the actual release datetime when available, not only the calendar date.
- Persist the timezone with every timestamp and keep the source-calendar timezone if it differs
  from the engine's storage timezone.
- Treat date-only data as incomplete for intraday analysis.
- Store FOMC statement time and press conference time separately when both are present.

## Scope Note

This is a taxonomy and default-proxy mapping only. It is not a trade recommendation and it does
not assume a single ETF must be used for every macro catalyst.
