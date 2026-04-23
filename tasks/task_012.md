id: T012
title: Dependency and env cleanup

objective:
  Normalize Python environment usage and dependency entry points in the repo.

context:
  Canonical runtime path needed because system python is not reliable in this
  environment (`python` may be unavailable while `.venv` is present).

inputs:
  - dependency files in repository
  - docs and script entrypoints

outputs:
  - Canonical `.venv` execution path documented
  - Dependency file inventory
  - Consolidation recommendation

prerequisites:
  - None

dependencies:
  - None

non_goals:
  - No packaging migration
  - No dependency version changes

requirements:
  - Document canonical python path
  - Identify legacy path patterns
  - Reduce ambiguity across docs/scripts

acceptance_criteria:
  - One clearly documented execution path
  - Legacy paths identified

tests:
  unit:
    - N/A (documentation)
  integration:
    - `.venv/bin/python` exists and resolves

definition_of_done:
  - Canonical path is documented in primary docs
  - Legacy path patterns are called out
  - Task marked complete in docs/TASKS.md

inventory:
  python_runtime:
    canonical:
      - /home/fabien/Documents/EarningsVolAnalysis/.venv/bin/python
    evidence:
      - docs/GETTING_STARTED.md
      - docs/USER_GUIDE.md
      - docs/OPERATOR_CHECKLIST.md
      - scripts/run_overnight_scan.sh
      - scripts/run_eod_refresh.sh
      - scripts/run_open_confirmation.sh
      - scripts/run_pre_market_scan.sh
  dependency_files:
    - event_vol_analysis/requirements.txt
  packaging_files_missing:
    - pyproject.toml
    - setup.cfg
    - Pipfile
    - environment.yml
  legacy_patterns_identified:
    - historical docs using generic `python -m ...` command examples

recommendation:
  - Keep `event_vol_analysis/requirements.txt` as the sole dependency source for
    now.
  - Keep `.venv/bin/python` as canonical in operator-facing docs and scripts.
  - Treat generic `python -m ...` usage as legacy/examples only unless explicitly
    mapped to `.venv/bin/python` in runbooks.

failure_modes:
  - N/A (documentation)
