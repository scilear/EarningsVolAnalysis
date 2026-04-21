id: T010
title: QuantConnect replay scaffold

objective:
  Export replay framework to QuantConnect for strategy backtesting.

context:
  QuantConnect is a popular backtesting platform. Need to export logic for external validation.

inputs:
  - T006 replay framework
  - QuantConnect API requirements

outputs:
  - QuantConnect-compatible export module
  - Strategy wrapper
  - Documentation for QC integration

prerequisites:
  - T002, T006 completed

dependencies:
  - T002, T006

non_goals:
  - Live trading on QuantConnect
  - Full platform integration

requirements:
  - Exportable strategy class
  - Event handling compatible with QC
  - Documentation of limitations

acceptance_criteria:
  - Strategy exports to QC format
  - Basic backtest runs
  - Documentation exists

tests:
  unit:
    - test_export_format
  integration:
    - Run basic backtest on QC

definition_of_done:
  - Export module complete
  - Task marked complete in docs/TASKS.md

notes:
  - TODO: ASK FABIEN for implementation details

failure_modes:
  - Missing method → raise NotImplementedError
  - Incompatible feature → document limitation