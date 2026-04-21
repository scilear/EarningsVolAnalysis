id: T032
title: Automated earnings season workflow

objective:
  Implement automated earnings season workflow with daily cron + Telegram notifications.

context:
  Need automated monitoring during earnings season.

inputs:
  - T029 batch report
  - T031 calibration loop
  - Cron schedule

outputs:
  - Daily cron job definition
  - Telegram bot integration
  - Alert thresholds

prerequisites:
  - T029, T031

dependencies:
  - T029, T031

non_goals:
  - No live trading execution

requirements:
  - Daily execution during earnings season
  - Telegram alerts for actionable events
  - Configurable thresholds
  - Manual trigger option

acceptance_criteria:
  - Cron job configured
  - Telegram messages sent
  - Manual trigger works

tests:
  unit:
    - test_telegram_message
    - test_alert_thresholds
  integration:
    - Full workflow execution

definition_of_done:
  - All tests pass
  - Task marked complete in docs/TASKS.md

notes:
  - Calibration task
  - TODO: ASK FABIEN for cron schedule

failure_modes:
  - Telegram unavailable → log only