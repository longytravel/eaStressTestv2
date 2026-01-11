---
phase: 01-specification
plan: 04
subsystem: specification
tags: [backtest, monte-carlo, reports, dashboard, leaderboard, boards]

# Dependency graph
requires:
  - phase: 01-specification plan 03
    provides: optimization-loop-spec (Steps 6-8B)
provides:
  - step-9-spec (batch backtest, gate conditions, composite score)
  - step-10-spec (Monte Carlo simulation, confidence/ruin gates)
  - step-11-spec (dashboard, leaderboard, boards generation)
affects: [01-05, 02-core-domain, 05-remaining-stages]

# Tech tracking
tech-stack:
  added: []
  patterns: [trade-extraction, equity-curve-split, composite-scoring, report-aggregation]

key-files:
  created:
    - .planning/phases/01-specification/specs/step-09-backtest-passes.md
    - .planning/phases/01-specification/specs/step-10-monte-carlo.md
    - .planning/phases/01-specification/specs/step-11-generate-reports.md
  modified: []

key-decisions:
  - "Monte Carlo runs on best pass only (workflow-level, not per-pass)"
  - "Leaderboard excludes stuck/failed workflows"
  - "Boards fall back to Step 5 metrics when workflow fails later"
  - "Dashboard requires refresh after Steps 12-13 to show new data"

patterns-established:
  - "Deterministic report naming prevents collision: S9_bt_pass{N}_{symbol}_{timeframe}_{timestamp}"
  - "Go Live Score weights: consistency 25%, profit 25%, trades 20%, PF 15%, DD 15%"
  - "Gate precedence: profit_factor, max_drawdown, minimum_trades (Step 9), mc_confidence, mc_ruin (Step 10)"

issues-created: []

# Metrics
duration: 8min
completed: 2026-01-11
---

# Phase 01-specification Plan 04: Analysis Steps Summary

**Complete specification for Steps 9-11: batch backtesting with per-pass gates and composite scoring, Monte Carlo simulation with confidence/ruin gates, and three-tier report generation (dashboard, leaderboard, boards)**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-01-11T19:35:00Z
- **Completed:** 2026-01-11T19:43:00Z
- **Tasks:** 3
- **Files created:** 3

## Accomplishments

- Documented Step 9 batch backtest with deterministic naming and composite score calculation
- Documented Step 10 Monte Carlo simulation methodology and gate conditions
- Documented Step 11 three-tier report system (dashboard, leaderboard, boards)
- Captured all gate thresholds: PF >= 1.5, DD <= 30%, trades >= 50, MC confidence >= 70%, ruin <= 5%
- Documented report refresh requirement after post-steps
- Documented fallback behaviors (boards to Step 5 metrics)

## Task Commits

Each task was committed atomically:

1. **Task 1: Document Step 9 (Backtest Top Passes)** - `a2aa3ff` (docs)
2. **Task 2: Document Step 10 (Monte Carlo)** - `5189996` (docs)
3. **Task 3: Document Step 11 (Generate Reports)** - `f0df35e` (docs)

## Files Created/Modified

- `.planning/phases/01-specification/specs/step-09-backtest-passes.md` - Batch backtest, gate conditions, trade extraction
- `.planning/phases/01-specification/specs/step-10-monte-carlo.md` - Monte Carlo methodology, confidence/ruin gates
- `.planning/phases/01-specification/specs/step-11-generate-reports.md` - Dashboard, leaderboard, boards structure

## Decisions Made

- **Monte Carlo scope:** Only computed for best pass (selected by score or profit), not per-pass
- **Leaderboard filtering:** Excludes failed/stuck workflows (awaiting_*, pending, failed)
- **Boards fallback:** Shows Step 5 validation metrics when workflow fails later
- **Report refresh:** Dashboard must be regenerated after Steps 12-13 to embed new data

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Step

Ready for 01-05-PLAN.md (Steps 12-14: Post-analysis steps - stress scenarios, forward windows, multi-pair)

---
*Phase: 01-specification*
*Completed: 2026-01-11*
