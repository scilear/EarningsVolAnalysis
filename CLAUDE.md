# CLAUDE.md

## Quick Commands

**Run analysis (test mode):**
```sh
.venv/bin/python -m event_vol_analysis.main --test-data --output reports/test_report.html
```

**Run analysis (live):**
```sh
.venv/bin/python -m event_vol_analysis.main --ticker NVDA --event-date 2026-05-28 --output reports/nvda_report.html
```

**Run tests:**
```sh
.venv/bin/python -m pytest event_vol_analysis/tests/
```

## Architecture

Package: `event_vol_analysis/`
CLI: `python -m event_vol_analysis.main`

See `docs/README.md` for full documentation.