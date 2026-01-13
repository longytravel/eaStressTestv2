---
phase: 05-remaining-stages
plan: 04
subsystem: stages
tags: [backtest, monte-carlo, simulation, gates, composite-score]

# Dependency graph
requires:
  - phase: 04-stage-framework
    provides: Stage protocol, StageResult, base patterns
  - phase: 05-remaining-stages/05-03
    provides: ParseResultsStage, SelectPassesStage for pass data
provides:
  - BacktestPassesStage for detailed pass backtesting
  - MonteCarloStage for sequence-dependency simulation
  - Complete optimization → Monte Carlo workflow stages
affects: [phase-6-pipeline, phase-7-compatibility, reports-stages]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Trade estimation from summary stats when actual trades unavailable
    - Gate aggregation (all gates must pass for success)
    - Best pass selection by configurable metric (score or profit)

key-files:
  created:
    - ea_stress/stages/s09_backtest_passes.py
    - ea_stress/stages/s10_monte_carlo.py
  modified:
    - ea_stress/stages/__init__.py

key-decisions:
  - "Estimate trades from summary stats when actual trade list unavailable"
  - "50% drawdown threshold for Monte Carlo ruin definition"
  - "Go Live Score calculation uses same formula as SelectPassesStage"

patterns-established:
  - "RESULT_FIELDS constant for filtering optimization params vs results"
  - "Monte Carlo shuffle-and-simulate pattern with configurable iterations"

issues-created: []

# Metrics
duration: 6min
completed: 2026-01-13
---

# Phase 5 Plan 4: Backtest Passes & Monte Carlo Summary

**BacktestPassesStage runs detailed backtests on selected passes with gate checks; MonteCarloStage shuffles trades 10000x to test sequence robustness**

## Performance

- **Duration:** 6 min
- **Started:** 2026-01-13T10:45:00Z
- **Completed:** 2026-01-13T10:51:00Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- BacktestPassesStage runs full backtests on all selected passes from Step 8B
- Gate checks per pass: profit_factor >= 1.5, max_drawdown <= 30%, min_trades >= 50
- Best pass selection by composite Go Live Score (or profit, configurable)
- MonteCarloStage shuffles trades N times to test sequence dependency
- Ruin probability calculation (50% drawdown threshold)
- Confidence intervals and percentiles for profit distribution

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement BacktestPassesStage** - `80188b7` (feat)
2. **Task 2: Implement MonteCarloStage** - `11a3345` (feat)
3. **Task 3: Export stages from package** - `5227a29` (chore)

## Files Created/Modified

- `ea_stress/stages/s09_backtest_passes.py` - BacktestPassesStage with gate checks and scoring
- `ea_stress/stages/s10_monte_carlo.py` - MonteCarloStage with shuffle simulation
- `ea_stress/stages/__init__.py` - Added lazy imports and exports

## Decisions Made

- **Trade estimation fallback:** When actual trade list unavailable, estimate from total_trades, win_rate, profit_factor
- **Ruin threshold:** 50% drawdown defines "ruin" in Monte Carlo simulation
- **Score calculation:** Same Go Live Score formula as SelectPassesStage for consistency

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## Next Phase Readiness

- BacktestPassesStage and MonteCarloStage ready for pipeline integration
- Remaining stages (11-14) needed: GenerateReports, StressScenarios, ForwardWindows, MultiPair
- Next plan: 05-05 (TBD - likely GenerateReportsStage)

---
*Phase: 05-remaining-stages*
*Completed: 2026-01-13*
