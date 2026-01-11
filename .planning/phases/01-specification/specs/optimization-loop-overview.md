# Optimization Loop Specification

## Overview

The optimization loop is a **single intelligent unit** that replaces the current fragmented Steps 6-8B:

| Current | New |
|---------|-----|
| Step 6: Create INI | `/optimization-loop` skill handles |
| Step 7: Run Optimization | internally, maintaining |
| Step 8: Parse Results | full context across |
| Step 8B: Select Passes (/stats-analyzer) | multiple optimization passes |

The loop's purpose is to find the **best parameter combinations** for an EA through iterative refinement, not just a single optimization run.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    /optimization-loop Skill                      │
│                                                                   │
│  ┌───────────────┐    ┌─────────────────┐    ┌───────────────┐ │
│  │ Python Engine │◄───│ Decision Layer  │◄───│ LLM Context   │ │
│  │ (deterministic)│    │ (LLM interprets)│    │ (full history)│ │
│  └───────┬───────┘    └────────┬────────┘    └───────────────┘ │
│          │                     │                                 │
│          ▼                     ▼                                 │
│  • INI generation        • When to loop?                        │
│  • MT5 execution         • When to proceed?                     │
│  • XML parsing           • Which params matter?                 │
│  • Stats computation     • Which ranges to refine?              │
│  • Reopt analysis        • Which passes to select?              │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principle: Hybrid Intelligence

**Python handles deterministic work:**
- INI file generation (exact format, no variation)
- MT5 terminal execution (subprocess, timeout handling)
- XML result parsing (structured data extraction)
- Statistical analysis (correlation, variance, clustering)

**LLM handles decision-making:**
- Interpreting statistical patterns ("what does this mean?")
- Deciding whether to loop or proceed ("is this good enough?")
- Refining parameter ranges ("which params are dead?")
- Selecting final passes ("which combinations to backtest?")

## Inputs

From Step 5 (Validate Trades):
- **validated EA**: Confirmed trading (met MIN_TRADES threshold)
- **initial_optimization_ranges**: ALL parameters with wide exploration ranges
- **wide_validation_params**: Used to prove EA trades (for reference)

From settings.py:
- Backtest period: 4 years (3 in-sample + 1 forward)
- Execution latency: 10ms
- Data model: 1-minute OHLC
- Optimization timeout: 10 hours (36000s)
- Deposit: £3000, Leverage: 100x
- MIN_TRADES: 50 (gate threshold)
- ONTESTER_MIN_TRADES: 10 (lower for genetic exploration)
- Forward mode: By date (ForwardMode=2)

## Outputs

To Step 9 (Backtest Top Passes):
- **selected_passes**: List of pass indices (typically top 20-30)
- **final_param_values**: Actual parameter values for each selected pass

Internal artifacts:
- **optimization_history**: All passes from all optimization runs
- **parameter_importance_analysis**: Which params correlate with success
- **refined_ranges**: The focused ranges used in final pass (if re-optimized)
- **reopt_analysis**: Toggle patterns, clustering, recommendations

## The Loop

```
                    ┌────────────────────────────┐
                    │   initial_optimization     │
                    │   _ranges (ALL params)     │
                    └─────────────┬──────────────┘
                                  │
                                  ▼
            ┌──────────────────────────────────────────┐
            │         PASS N EXECUTION                  │
            │                                           │
            │  1. Generate INI (Python)                 │
            │     • Convert ranges to MT5 format        │
            │     • Handle boolean toggles correctly    │
            │     • Set fixed params (safety, etc.)     │
            │                                           │
            │  2. Run Optimization (MT5)                │
            │     • Genetic algorithm (mode=2)          │
            │     • Progress logging every 60s          │
            │     • Timeout: 10 hours                   │
            │                                           │
            │  3. Parse Results (Python)                │
            │     • XML to structured data              │
            │     • Merge forward/back results          │
            │     • Filter by ONTESTER_MIN_TRADES       │
            │                                           │
            │  4. Analyze Parameters (Python)           │
            │     • Toggle patterns (True vs False)     │
            │     • Continuous clustering (CV)          │
            │     • Generate reopt recommendation       │
            │                                           │
            └─────────────────────┬────────────────────┘
                                  │
                                  ▼
            ┌──────────────────────────────────────────┐
            │        DECISION POINT (LLM)               │
            │                                           │
            │  Given: Parameter importance analysis     │
            │  Decide: LOOP or PROCEED?                 │
            │                                           │
            │  Decision factors:                        │
            │  • Pass number (1 = usually loop)         │
            │  • Quality of results                     │
            │  • Parameter clarity                      │
            │  • Diminishing returns                    │
            │                                           │
            │  After Pass 1: Usually recommend LOOP     │
            │  After Pass 2: PAUSE for user discussion  │
            │                                           │
            └─────────────────────┬────────────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
              ▼                                       ▼
    ┌─────────────────┐                    ┌─────────────────┐
    │     LOOP        │                    │    PROCEED      │
    │                 │                    │                 │
    │ Refine ranges:  │                    │ Select passes:  │
    │ • Remove dead   │                    │ • Top N by      │
    │   params        │                    │   Go Live Score │
    │ • Narrow        │                    │ • Consider      │
    │   clusters      │                    │   diversity     │
    │ • Fix toggle    │                    │ • Both back+    │
    │   winners       │                    │   forward       │
    │                 │                    │   positive      │
    └────────┬────────┘                    └────────┬────────┘
             │                                      │
             │                                      ▼
             │                           ┌─────────────────┐
             │                           │   To Step 9     │
             │                           │   (Backtest)    │
             └──────────► Loop ──────────┘─────────────────┘
                         back to
                         PASS N+1
```

## Constraints

**HARD LIMITS (enforced by runner):**
- `REOPT_MAX_ITERATIONS = 2`: Cannot exceed 2 re-optimization passes
- Must run `reopt_analysis` before proceeding either direction
- Cannot skip optimization if params found

**SOFT THRESHOLDS (LLM can override with reasoning):**
- `REOPT_TOGGLE_THRESHOLD = 0.70`: 70% of top passes same value = pattern
- `REOPT_CLUSTERING_CV_THRESHOLD = 0.20`: CV < 0.2 = tight clustering
- `REOPT_MIN_VALID_PASSES = 50`: Fewer suggests widen ranges

## Deprecations

The `/stats-analyzer` skill is **deprecated** and absorbed into `/optimization-loop`:
- Pass selection logic remains the same
- Full optimization context now available
- No more context-switching between skills
- Reopt analysis integrated with selection

## Integration Points

**Before (Step 5):**
- Receives validated EA + initial_optimization_ranges
- EA has been proven to trade via wide_validation_params

**After (Step 9):**
- Provides selected_passes with parameter values
- Step 9 backtests each pass for equity curves + Monte Carlo

**Dashboard/Reports:**
- optimization_history available for analysis
- parameter_importance visible in UI
- Shows which ranges were refined and why
