# Step 14: Multi-Pair Specification

## Overview

Step 14 runs the complete workflow on additional trading symbols using the same EA and parameter configuration. Each symbol gets its own full optimization, not just a backtest with the primary symbol's parameters.

**Gate**: None (informational step, does not fail the workflow)
**Auto-run**: Controlled by `settings.AUTO_RUN_MULTI_PAIR` (default: False)
**Runs after**: Step 13 (Forward Windows) or earlier if forward windows is disabled

## Purpose

1. Test EA generalization across multiple currency pairs
2. Identify symbol-specific optimization opportunities
3. Build a portfolio view of the same strategy
4. Validate that the strategy isn't overfitted to a single symbol

## Input

From workflow state:
- `ea_path`: Original EA source file
- `wide_validation_params`: Validation parameters from Step 4
- `param_ranges`: Optimization ranges from Step 4
- `timeframe`: Same timeframe as parent workflow
- `terminal`: MT5 terminal configuration

From settings:
- `settings.MULTI_PAIR_SYMBOLS`: List of symbols to test (default: `["EURUSD", "USDJPY"]`)

## Execution Model

### Parent/Child Workflow Relationship

```
Parent Workflow (GBPUSD)
├── Steps 1-13: Complete workflow
└── Step 14: Multi-Pair
    ├── Child Workflow 1 (EURUSD)
    │   ├── Steps 1-3: Load, compile, extract
    │   ├── Continue with parent's params/ranges
    │   └── Steps 5-13: Full optimization cycle
    └── Child Workflow 2 (USDJPY)
        ├── Steps 1-3: Load, compile, extract
        ├── Continue with parent's params/ranges
        └── Steps 5-13: Full optimization cycle
```

### Key Behaviors

1. **Symbol Filtering**: Parent symbol is automatically excluded from the list
2. **Full Optimization**: Each child runs its own genetic optimization (not just backtest)
3. **Parameter Reuse**: Children use the same `wide_validation_params` and `optimization_ranges`
4. **No Recursion**: Children have `auto_run_multi_pair=False` to prevent infinite loops
5. **Independent State**: Each child creates its own workflow state file

## Child Workflow Creation

```python
child = WorkflowRunner(
    ea_path=parent.ea_path,
    terminal_name=parent.terminal.get('name'),
    symbol=child_symbol,  # e.g., "EURUSD"
    timeframe=parent.timeframe,
    auto_run_stress_scenarios=True,
    auto_stats_analysis=True,
    auto_run_forward_windows=True,
    auto_run_multi_pair=False,  # Prevent recursion!
    on_progress=parent.on_progress,
)
```

### Execution Flow

```python
# Phase 1: Load and prepare
child.run(stop_on_failure=False, pause_for_analysis=True)

# Phase 2: Continue with parent's parameters
summary = child.continue_with_params(
    wide_validation_params=parent.wide_validation_params,
    optimization_ranges=parent.param_ranges,
    stop_on_failure=False,
)
```

## Skip Conditions

Step 14 is skipped when:
- No additional symbols configured (empty list or only parent symbol)
- No stored params/ranges available (Step 4 not completed)

Skipped outputs:
```python
{
    "success": True,
    "skipped": True,
    "reason": "No additional symbols configured"
}
```

```python
{
    "success": True,
    "skipped": True,
    "reason": "No stored params/ranges available for multi-pair"
}
```

## Output Structure

```python
{
    "success": True,
    "symbol_count": 2,
    "symbols": ["EURUSD", "USDJPY"],
    "runs": [
        {
            "symbol": "EURUSD",
            "workflow_id": "MyEA_EURUSD_H1_20260111_123456",
            "status": "completed",
            "dashboard_path": "runs/dashboards/MyEA_EURUSD_H1_20260111_123456/index.html",
            "leaderboard_path": "runs/leaderboard/index.html",
            "boards_path": "runs/boards/index.html",
            "composite_score": 72.5,
            "go_live": True,
        },
        {
            "symbol": "USDJPY",
            "workflow_id": "MyEA_USDJPY_H1_20260111_123789",
            "status": "completed",
            "dashboard_path": "runs/dashboards/MyEA_USDJPY_H1_20260111_123789/index.html",
            "leaderboard_path": "runs/leaderboard/index.html",
            "boards_path": "runs/boards/index.html",
            "composite_score": 65.0,
            "go_live": True,
        },
    ],
    "boards_path": "runs/boards/index.html",
}
```

### Error Handling

If a child workflow fails:
```python
{
    "symbol": "USDJPY",
    "success": False,
    "error": "Error message describing the failure"
}
```

The parent workflow continues with other symbols even if one fails.

## Dashboard/Boards Integration

### Parent Dashboard

The parent workflow's dashboard shows:
- Summary of multi-pair runs
- Links to each child workflow's dashboard
- Comparison table of composite scores across symbols

### Boards Index

The global Boards index (`runs/boards/index.html`) shows:
- All workflows including children
- Children are visually linked to parent
- Portfolio-level aggregation available

### Leaderboard

Each child workflow appears separately on the leaderboard:
- Independent ranking based on its own performance
- Symbol column identifies the currency pair
- Same EA with different symbols can have varying scores

## Execution Time Considerations

Multi-pair execution is expensive:
- Each symbol runs full optimization (hours per symbol)
- Stress scenarios add significant time per symbol
- Total time = N symbols x (optimization + backtests + stress)

This is why `AUTO_RUN_MULTI_PAIR = False` by default.

### Performance Estimate

For a typical workflow:
| Step | Time per Symbol |
|------|-----------------|
| Steps 1-5 | ~5 minutes |
| Step 6-8 | 2-10 hours (optimization) |
| Step 9 | ~30 minutes (backtests) |
| Steps 10-11 | ~5 minutes |
| Step 12 | ~1-2 hours (stress) |
| Step 13 | <1 minute |

Total per additional symbol: **3-13 hours**

## Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `AUTO_RUN_MULTI_PAIR` | `False` | Auto-run after Step 13 |
| `MULTI_PAIR_SYMBOLS` | `["EURUSD", "USDJPY"]` | Symbols to test |

## Key Implementation Files

- `engine/runner.py`: `_step_multi_pair()` method
- `engine/state.py`: Separate state files per workflow

## Parent Symbol Handling

The parent symbol is automatically filtered out:
```python
symbols = [s for s in symbols if s != self.symbol.upper()]
```

This prevents:
- Duplicate optimization of the same symbol
- Confusion in the boards/leaderboard
- Wasted computation

## Use Cases

### 1. Portfolio Building
Test if a GBPUSD strategy works on correlated pairs:
```python
MULTI_PAIR_SYMBOLS = ["EURUSD", "GBPJPY", "EURGBP"]
```

### 2. Pair Comparison
Compare performance across major pairs:
```python
MULTI_PAIR_SYMBOLS = ["EURUSD", "USDJPY", "GBPUSD", "USDCHF", "AUDUSD"]
```

### 3. Regional Testing
Test if strategy works across different session currencies:
```python
# Asian session pairs
MULTI_PAIR_SYMBOLS = ["USDJPY", "AUDJPY", "NZDJPY"]

# European pairs
MULTI_PAIR_SYMBOLS = ["EURUSD", "EURGBP", "EURJPY"]
```

## Programmatic Control

Override default symbols per workflow:
```python
runner = WorkflowRunner(
    ea_path="path/to/EA.mq5",
    symbol="GBPUSD",
    timeframe="H1",
    multi_pair_symbols=["EURUSD", "USDJPY", "AUDUSD"],
    auto_run_multi_pair=True,
)
```

## Post-Step Behavior

After running all symbols:
1. Results saved to `state.multi_pair_runs`
2. Boards regenerated to show all child workflows
3. No leaderboard regeneration (children update it individually)

---
*Step: 14*
*Category: Post-analysis*
*Gate: None (informational)*
*Optional: Yes (default disabled)*
