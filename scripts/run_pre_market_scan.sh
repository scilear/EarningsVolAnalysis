#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/fabien/Documents/EarningsVolAnalysis"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
LOG_PATH="${PROJECT_DIR}/logs/pre_market_scan.log"

mkdir -p "${PROJECT_DIR}/logs"

if [[ -f "${PROJECT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/.env"
fi

timestamp="$(date -Iseconds)"
echo "${timestamp} pre_market_scan start" >> "${LOG_PATH}"

set +e
"${VENV_PYTHON}" -m event_vol_analysis.workflow.daily_scan \
  --mode pre-market \
  --date "$(date +%Y-%m-%d)" \
  "$@"
exit_code=$?
set -e

timestamp_end="$(date -Iseconds)"
echo "${timestamp_end} pre_market_scan exit_code=${exit_code}" >> "${LOG_PATH}"

exit "${exit_code}"
