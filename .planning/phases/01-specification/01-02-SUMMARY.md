---
phase: 01-specification
plan: 02
subsystem: specification
tags: [params, validation, trades, mql5-fixer, param-analyzer]

# Dependency graph
requires:
  - phase: 01-specification plan 01
    provides: step-3-spec (parameter extraction and pause point)
provides:
  - step-4-spec (Analyze Params with ALL-param contract)
  - step-5-spec (Validate Trades with MIN_TRADES gate)
  - step-5b-spec (Fix EA retry loop)
affects: [01-03, 02-core-domain, 07-compatibility-shim]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created:
    - .planning/phases/01-specification/specs/step-04-analyze-params.md
    - .planning/phases/01-specification/specs/step-05-validate-trades.md
    - .planning/phases/01-specification/specs/step-05b-fix-ea.md
  modified: []

key-decisions:
  - "/param-analyzer must produce ALL-param initial_optimization_ranges for exploration (refinement after Step 8)"
  - "wide_validation_params maximize trades to PROVE EA can trade"
  - "Step 5B is a retry loop (max 3 attempts) before workflow failure"

patterns-established:
  - "LLM integration points documented with skill contracts and resume mechanisms"
  - "Gate conditions include settings.py references for threshold values"

issues-created: []

# Metrics
duration: 12min
completed: 2026-01-11
---

# Phase 01-specification Plan 02: Parameter Setup Summary

**Complete specifications for Steps 4-5B (Analyze Params, Validate Trades, Fix EA) with updated /param-analyzer contract for ALL-param exploration and /mql5-fixer retry loop**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-01-11T19:15:00Z
- **Completed:** 2026-01-11T19:27:00Z
- **Tasks:** 3
- **Files created:** 3

## Accomplishments

- Documented Step 4 (Analyze Params) with UPDATED contract requiring ALL parameters in initial_optimization_ranges
- Documented parameter inclusion/exclusion criteria (only skip identifiers, cosmetics, debug)
- Documented toggle-dependency rules for optimization
- Documented Step 5 (Validate Trades) with MIN_TRADES gate and safety parameter loosening
- Documented Step 5B (Fix EA) retry mechanism with max 3 attempts
- Captured both LLM skill contracts: `/param-analyzer` and `/mql5-fixer`
- Defined clear handoff point: validated EA + initial ranges → optimization loop

## Task Commits

Each task was committed atomically:

1. **Task 1: Document Step 4 (Analyze Params)** - `89b1ca1` (docs)
2. **Task 2: Document Step 5 (Validate Trades)** - `db543a5` (docs)
3. **Task 3: Document Step 5B (Fix EA)** - `a8fac34` (docs)

## Files Created/Modified

- `.planning/phases/01-specification/specs/step-04-analyze-params.md` - First LLM integration point with ALL-param contract
- `.planning/phases/01-specification/specs/step-05-validate-trades.md` - Validation backtest with MIN_TRADES gate
- `.planning/phases/01-specification/specs/step-05b-fix-ea.md` - EA fix retry loop with /mql5-fixer integration

## Decisions Made

- `/param-analyzer` must produce ALL-param ranges for initial exploration — refinement happens after Step 8 via optimization loop, not during initial analysis
- wide_validation_params purpose is to PROVE the EA can trade, not to optimize
- Step 5B fix loop prerequisite: optimization loop expects a working EA

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Step

Ready for 01-03-PLAN.md (Optimization Loop specifications - Steps 6-8B)

---
*Phase: 01-specification*
*Completed: 2026-01-11*
