# AGENTS.md

**High-Signal Project Guide for Agent Developers**

This file contains only repo-specific, non-obvious instructions to ensure agents work correctly and avoid mistakes. Omit generic Python guidance.

---

## Key Project Facts

- **Single package:** All main code in `event_vol_analysis/`. No monorepo or subpackages.
- **All runs use venv:** Always invoke commands as `.venv/bin/python ...` from the repo root.
- **Reports, not stdout:** Analysis always writes to an explicit output file in `/reports/`—never to the console or an implicit path.

---

## Essential Developer Commands

- **Install requirements:**
  ```sh
  .venv/bin/python -m pip install -r event_vol_analysis/requirements.txt
  ```

- **Run analysis (test data):**
  ```sh
  .venv/bin/python -m event_vol_analysis.main --test-data --output reports/test_report.html
  ```

- **Run analysis (example live):**
  ```sh
  .venv/bin/python -m event_vol_analysis.main --ticker NVDA --event-date 2026-05-28 --output reports/nvda_report.html
  ```

- **Run tests:**
  ```sh
  .venv/bin/python -m pytest event_vol_analysis/tests/
  ```

- **Lint code (must pass before commit/PR):**
  ```sh
  pip install flake8
  flake8 .
  # Optional: black . ; isort .
  ```

- **Docs start:** `docs/README.md`  (Operator workflows: `docs/USER_GUIDE.md`)

---

## Important Conventions / Gotchas

- **ALWAYS** use `python -m event_vol_analysis.main` (never direct script invocation).
- **ALWAYS** pass `--output` explicitly for all runs. Reports save to `/reports/` only, never default/console.
- All tests must live in (or under) `event_vol_analysis/tests/`, named using standard pytest/unittest patterns.
- Lint and format before all PRs/commits. Code style and import order are checked in CI/pull review.
- No data is hardcoded: input/output paths must be CLI args or config-driven.
- Package configuration is in `event_vol_analysis/config.py` (pure constants, no dynamic/env logic).
- No pyproject.toml or setup.py; install only via requirements.txt.

---

## BMAD/Agentic Infrastructure (if using BMAD agents)

- Before running any BMAD agent workflow, always load `_bmad/bmm/config.yaml`.
- BMAD agent/role and workflow definitions are in `.github/agents/`, `.github/prompts/`, and under `_bmad/`.
- Outputs, planning, and implementation artifacts for BMAD workflows save to `_bmad-output/` in project root.

---

## References
- For full usage, see `docs/README.md` and `docs/USER_GUIDE.md`.
- If in doubt, prefer logic/data from scripts, config, and main README over markdown docs.

_Last updated: 2026-05-22. Update if any project structure, workflow, or conventions change._
