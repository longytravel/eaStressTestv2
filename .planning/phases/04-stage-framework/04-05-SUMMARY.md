---
phase: 04-stage-framework
plan: 05
subsystem: stages
tags: [backtest, validation, mt5, trades, gate]

# Dependency graph
requires:
  - phase: 04-stage-framework
    provides: Stage protocol, StageResult, CompileStage, ExtractParamsStage, AnalyzeParamsStage
provides:
  - ValidateTradesStage for trade validation backtest
  - minimum_trades gate check
  - Complete Stage 1-5 implementation
affects: [phase-05-remaining-stages, optimization-workflow]

# Tech tracking
tech-stack:
  added: []
  patterns: [validation-backtest-stage, safety-param-overrides]

key-files:
  created: [ea_stress/stages/s05_validate_trades.py]
  modified: [ea_stress/stages/__init__.py]

key-decisions:
  - "Loose safety limits for validation (500 pips spread/slippage)"
  - "Gate uses MIN_TRADES setting (default 50)"

patterns-established:
  - "Safety param overrides for different run modes (validation vs optimization)"

issues-created: []

# Metrics
duration: 2min
completed: 2026-01-12
---

# Phase 4 Plan 5: ValidateTradesStage Summary

**Stage 5 validation backtest with minimum_trades gate using wide params and loose safety limits**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-12T20:47:07Z
- **Completed:** 2026-01-12T20:49:20Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- ValidateTradesStage class implementing Stage protocol
- Runs backtest with wide_validation_params from Step 4
- Applies loose safety limits (500 pips spread/slippage) for validation
- Creates minimum_trades gate checking against MIN_TRADES setting
- All 7 stage classes now exported from ea_stress.stages

## Task Commits

1. **Task 1: Implement ValidateTradesStage** - `f51bbd2` (feat)
2. **Task 2: Export ValidateTradesStage** - `48c0c70` (chore)

## Files Created/Modified

- `ea_stress/stages/s05_validate_trades.py` - ValidateTradesStage implementation
- `ea_stress/stages/__init__.py` - Added ValidateTradesStage export

## Decisions Made

- Used loose safety limits (500 pips) for validation to maximize trade generation
- Gate checks against settings.MIN_TRADES (default 50)
- Deterministic report naming: `S5_validate_{symbol}_{timeframe}_{workflow_id[:8]}`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## Next Phase Readiness

- Phase 4 (Stage Framework) complete - all 5 plans executed
- 7 stage classes implemented: LoadEA, InjectOnTester, InjectSafety, Compile, ExtractParams, AnalyzeParams, ValidateTrades
- Ready for Phase 5: Remaining Stages (Steps 5B-14)

---
*Phase: 04-stage-framework*
*Completed: 2026-01-12*
