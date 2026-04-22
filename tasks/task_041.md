id: T041
title: CLI Integration + Agent Skill Update

objective:
  Wire structure_advisor.py into the earningsvol CLI as an earningsvol query
  subcommand, and update the vol-specialist agent skill documentation to
  reference it as the canonical option structure query method — replacing
  inline chain loading.

context:
  T039 and T040 build the engine. T041 makes it callable from the command
  line and wires it into the agent workflow. The test of success: a session
  like the Apr 22 GLD diagonal analysis (3 rounds of chain loading, inline
  pricing) becomes a single earningsvol query call returning a pre-built
  table. Full design spec: docs/STRUCTURE_ADVISOR_SPEC.md.

inputs:
  - T040: query_structures() and StructureAdvisorResult.to_table()
  - Existing CLI entry point (main.py or equivalent)
  - agents/vol-specialist/persona.md in InvestmentDeskAgents repo
    (DATA TOOLS section)

outputs:
  - earningsvol query subcommand with flags:
      --payoff {crash,rally,sideways,vol-expansion,vol-compression,
                directional-convex}
      --ticker TICKER
      --expiry YYYY-MM-DD
      --spot FLOAT
      --budget FLOAT          (optional)
      --iv-percentile FLOAT   (optional, passed into context)
      --validate STRUCTURE    (optional, see below)
      --output {table,json}   (default: table)
  - --validate flag: accepts a structure description string (e.g.
    "diagonal:short-May15-420P/long-2x-Jul17-410P"); prices that specific
    structure alongside the ranked candidates and marks it for comparison
  - --output json: returns StructureAdvisorResult as JSON for programmatic
    consumption by the agent
  - Updated vol-specialist persona.md DATA TOOLS section documenting
    earningsvol query as canonical option structure pricing method

prerequisites:
  - T040 (structure_advisor.py core)

dependencies:
  - T040

non_goals:
  - No interactive mode or wizard
  - No changes to existing earningsvol subcommands (analyze, batch, etc.)
  - No Telegram alerting for structure queries (that is the earnings workflow)
  - Do not modify InvestmentDeskAgents repo beyond persona.md DATA TOOLS
    section — the agent skill update is documentation only

requirements:
  - earningsvol query must accept all flags listed above
  - Default output (--output table) prints StructureAdvisorResult.to_table()
    directly to stdout — ≤60 lines, no other output
  - --output json prints the full StructureAdvisorResult as JSON (all
    dataclass fields serialized)
  - --validate parses the structure string and adds the specified structure
    to the comparison (even if not in the standard map for that payoff type)
    with a MANUALLY_SPECIFIED label in the output
  - Exit codes: 0 on success, 1 on pricing failure (chain unavailable),
    2 on invalid arguments
  - persona.md DATA TOOLS section change: add earningsvol query entry with
    example command and note that it replaces inline chain loading for
    structure pricing; keep existing option_chain.py and iv_rank.py entries
    (they remain valid for raw data needs)

acceptance_criteria:
  - earningsvol query --payoff crash --ticker GLD --expiry 2026-05-15
    --spot 429.57 produces table output in ≤60 lines
  - earningsvol query --payoff crash --ticker GLD --expiry 2026-05-15
    --spot 429.57 --output json produces valid JSON
  - earningsvol query --payoff crash --ticker GLD --expiry 2026-05-15
    --spot 429.57 --validate "diagonal:short-May15-420P/long-2x-Jul17-410P"
    includes the diagonal in the comparison table with MANUALLY_SPECIFIED label
  - earningsvol query --payoff invalid exits with code 2 and usage message
  - persona.md DATA TOOLS section updated with earningsvol query entry

tests:
  unit:
    - test_cli_query_table_output_under_60_lines
    - test_cli_query_json_output_valid
    - test_cli_query_invalid_payoff_exits_2
    - test_cli_query_validate_flag_adds_structure
    - test_cli_query_budget_flag_passed_to_advisor
  integration:
    - Full CLI invocation with mocked chain data → table output printed,
      exit code 0

definition_of_done:
  - earningsvol query subcommand functional with all flags
  - --output json works
  - --validate flag parses and includes specified structure
  - persona.md DATA TOOLS section updated
  - All unit and integration tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - The --validate flag is the highest-value use case from the agent's
    perspective: "I have a structure in mind, confirm it against the
    alternatives." The ranking table always shows the user-specified
    structure vs. the canonical candidates — this is what replaces the
    multi-round adversarial pricing loop.
  - persona.md change should be minimal — one entry under DATA TOOLS, one
    example command, one sentence on when to use it vs option_chain.py.
    Do not restructure the persona.

failure_modes:
  - Chain unavailable at CLI time → print "DATA UNAVAILABLE: option chain
    fetch failed" to stderr, exit 1
  - --validate structure string unparseable → print parse error to stderr,
    exit 2
  - earningsvol not on PATH in agent environment → fallback: agent uses
    option_chain.py directly until PATH issue resolved; document in
    GETTING_STARTED.md
