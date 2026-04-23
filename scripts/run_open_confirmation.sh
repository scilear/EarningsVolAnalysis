#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/fabien/Documents/EarningsVolAnalysis"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
LOG_PATH="${PROJECT_DIR}/logs/open_confirmation.log"

mkdir -p "${PROJECT_DIR}/logs"

if [[ -f "${PROJECT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  source "${PROJECT_DIR}/.env"
fi

timestamp="$(date -Iseconds)"
echo "${timestamp} open_confirmation start" >> "${LOG_PATH}"

set +e
"${VENV_PYTHON}" -m event_vol_analysis.workflow.daily_scan \
  --mode open-confirmation \
  --refresh-cache \
  --date "$(date +%Y-%m-%d)" \
  "$@"
exit_code=$?
set -e

timestamp_end="$(date -Iseconds)"
echo "${timestamp_end} open_confirmation exit_code=${exit_code}" >> "${LOG_PATH}"

exit "${exit_code}"