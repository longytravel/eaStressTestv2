# Step 12: Stress Scenarios Specification

## Overview

Step 12 runs post-workflow stress tests to verify EA robustness under different execution conditions. This is an infrastructure-level step that works for any EA without modification.

**Gate**: None (informational step, does not fail the workflow)
**Auto-run**: Controlled by `settings.AUTO_RUN_STRESS_SCENARIOS` (default: True)
**Runs after**: Step 11 (Generate Reports)

## Purpose

1. Validate performance across different time windows (recent vs historical)
2. Compare tick-based execution vs OHLC models
3. Test latency sensitivity for tick-model scenarios
4. Compute cost overlays (spread/slippage) without additional MT5 runs

## Input

From workflow state:
- `compiled_ea_path`: Path to compiled .ex5
- `symbol`: Trading symbol (e.g., "GBPUSD")
- `timeframe`: Chart timeframe (e.g., "H1")
- `backtest_results.input_params`: Fixed parameters from best pass (Step 9)
- `backtest_results.report_path`: Baseline report for overlay calculations
- `backtest_dates`: Workflow date range for anchoring windows

## Dynamic Scenario Generation

When `settings.STRESS_SCENARIOS` is None (default), the suite is generated dynamically using `build_dynamic_scenarios()`.

### Window Types

All windows are anchored to the workflow end date for reproducibility.

#### Rolling Windows (settings.STRESS_WINDOW_ROLLING_DAYS)

Default: `[7, 14, 30, 60, 90]`

| Window ID | Label | Calculation |
|-----------|-------|-------------|
| `last_7d` | Last 7 days | `end_date - 7 days` to `end_date` |
| `last_14d` | Last 14 days | `end_date - 14 days` to `end_date` |
| `last_30d` | Last 30 days | `end_date - 30 days` to `end_date` |
| `last_60d` | Last 60 days | `end_date - 60 days` to `end_date` |
| `last_90d` | Last 90 days | `end_date - 90 days` to `end_date` |

#### Calendar Month Windows (settings.STRESS_WINDOW_CALENDAR_MONTHS_AGO)

Default: `[1, 2, 3]`

| Value | Label | Calculation |
|-------|-------|-------------|
| 1 | Last full month (e.g., "Dec 2025") | First to last day of previous month |
| 2 | Two months ago (e.g., "Nov 2025") | First to last day of that month |
| 3 | Three months ago (e.g., "Oct 2025") | First to last day of that month |

### Model Types (settings.STRESS_WINDOW_MODELS)

Default: `[1, 0]` - Both OHLC and Tick models

| Model | Name | Description |
|-------|------|-------------|
| 0 | Tick | Every tick (real or generated) |
| 1 | OHLC | 1-minute OHLC data |

Each window runs with both models, producing scenario IDs like:
- `ohlc_last_30d`
- `tick_last_30d`
- `ohlc_month_2025_12`
- `tick_month_2025_12`

### Tick-Only Latency Variants (settings.STRESS_TICK_LATENCY_MS)

Default: `[250, 5000]`

For tick-model scenarios only, additional latency variants are added:
- `tick_last_30d_latency_250ms`
- `tick_last_30d_latency_5000ms`

These test how the EA performs with execution delays.

## Scenario Execution

Each base scenario (excluding overlays) runs a full MT5 backtest:

```python
run_backtest(
    compiled_ea_path,
    symbol=symbol,
    timeframe=timeframe,
    params=params,           # From best pass
    from_date=window_start,
    to_date=window_end,
    model=model,             # 0 or 1
    execution_latency_ms=latency,
    spread=spread_points,    # Usually None
    report_name=deterministic_name,
    terminal=terminal,
    timeout=timeout_per_scenario,  # Default 900 seconds
    extract_equity=False,
)
```

### Deterministic Report Naming

Report names are generated to prevent collisions:
```
{ea_stem}_S12_{scenario_id}_{hash8}
```

The hash is computed from `sha1(ea_stem:scenario_id)[:8]` ensuring uniqueness.

## Tick File Coverage Validation

For tick-model scenarios (model=0), the system performs a side-channel validation:

1. Locate MT5 tick storage: `<data_path>/bases/<server>/ticks/<SYMBOL>/`
2. Check for monthly `.tkc` files covering the window
3. Flag if months are missing (MT5 may synthesize ticks, hiding data gaps)

Output fields:
- `tick_files_ok`: Boolean, True if all months have `.tkc` files
- `tick_files_missing`: List of missing month IDs (e.g., `["202512"]`)

This supplements MT5's "History Quality %" which can show 100% even without real tick data.

## Cost Overlays (Post-Hoc Computation)

When `settings.STRESS_INCLUDE_OVERLAYS = True` (default), spread/slippage impacts are computed from trade lists without additional MT5 runs.

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `STRESS_OVERLAY_SPREAD_PIPS` | `[0.0, 1.0, 2.0, 3.0, 5.0]` | Spread values to test |
| `STRESS_OVERLAY_SLIPPAGE_PIPS` | `[0.0, 1.0, 3.0]` | Slippage per side |
| `STRESS_OVERLAY_SLIPPAGE_SIDES` | `2` | Apply to entry + exit |

### Calculation Method

1. Extract trades from base scenario report
2. Estimate pip value per lot from trade data
3. For each spread/slippage combination:
   - Calculate extra cost: `(spread + slippage * sides) * pip_value * volume`
   - Adjust each trade's net profit
   - Recompute metrics (profit, PF, drawdown)

Overlay scenario IDs: `{base_id}_overlay_sp{spread}_sl{slip}`

### Pip Value Estimation

The system infers pip value per lot from the trade list:
1. Determine pip size from symbol (0.0001 for most, 0.01 for JPY pairs)
2. Calculate pip value from gross profit / pips moved / volume
3. Use median across trades for robustness

## Output Structure

```python
{
    "success": True,
    "pass_num": 42,  # Best pass from Step 9
    "scenario_count": 156,  # Total including overlays
    "baseline": {
        "pass_num": 42,
        "profit": 2500.0,
        "profit_factor": 2.1,
        "max_drawdown_pct": 12.5,
        "total_trades": 150,
        "report_path": "path/to/baseline.html",
        "settings": {
            "from_date": "2022.01.01",
            "to_date": "2026.01.10",
            "model": 1,
            "execution_latency_ms": 10,
        }
    },
    "scenarios": [
        {
            "id": "ohlc_last_30d",
            "label": "OHLC (1m) - Last 30 days",
            "period": "last_30d",
            "window": {
                "id": "last_30d",
                "label": "Last 30 days",
                "from_date": "2025.12.11",
                "to_date": "2026.01.10",
            },
            "tags": ["window", "ohlc"],
            "variant": "base",  # or "overlay"
            "settings": {
                "from_date": "2025.12.11",
                "to_date": "2026.01.10",
                "model": 1,
                "execution_latency_ms": 10,
                "spread_points": None,
            },
            "report_name": "MyEA_S12_ohlc_last_30d_a1b2c3d4",
            "success": True,
            "result": {
                "profit": 450.0,
                "profit_factor": 1.8,
                "max_drawdown_pct": 8.5,
                "total_trades": 25,
                "history_quality_pct": 100.0,
                "bars": 720,
                "ticks": 0,
                "tick_files_ok": None,  # Only for tick model
                "tick_files_missing": None,
            },
            "gates": {
                "profit_factor": {"passed": True, "value": 1.8, "threshold": 1.5},
                "max_drawdown": {"passed": True, "value": 8.5, "threshold": 30.0},
                "minimum_trades": {"passed": False, "value": 25, "threshold": 50},
            },
            "score": 0.65,
            "errors": [],
            "report_path": "path/to/S12_report.html",
            "xml_path": "path/to/S12_report.xml",
        },
        # ... more scenarios
    ]
}
```

## Dashboard Display

Stress results appear in the workflow dashboard as:
1. A dedicated "Stress Scenarios" table with sortable columns
2. Baseline row (from Step 9) for comparison
3. Color-coded gates (pass/fail per scenario)
4. Tick file coverage warnings for tick-model scenarios

## Leaderboard Integration

The Leaderboard includes a "Stress" column showing:
- Aggregated stress test status for the workflow
- Tooltip with scenario counts and pass/fail summary
- Only populated for workflows that completed Step 12

## Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `AUTO_RUN_STRESS_SCENARIOS` | `True` | Auto-run after Step 11 |
| `STRESS_SCENARIOS` | `None` | Override list (None = dynamic) |
| `STRESS_WINDOW_ROLLING_DAYS` | `[7, 14, 30, 60, 90]` | Rolling window sizes |
| `STRESS_WINDOW_CALENDAR_MONTHS_AGO` | `[1, 2, 3]` | Calendar month offsets |
| `STRESS_WINDOW_MODELS` | `[1, 0]` | Models per window |
| `STRESS_TICK_LATENCY_MS` | `[250, 5000]` | Tick latency variants (ms) |
| `STRESS_INCLUDE_OVERLAYS` | `True` | Enable cost overlays |
| `STRESS_OVERLAY_SPREAD_PIPS` | `[0.0, 1.0, 2.0, 3.0, 5.0]` | Spread values |
| `STRESS_OVERLAY_SLIPPAGE_PIPS` | `[0.0, 1.0, 3.0]` | Slippage values |
| `STRESS_OVERLAY_SLIPPAGE_SIDES` | `2` | Sides for slippage |
| `PIP_TO_POINTS` | `10` | Pips to points conversion |

## Post-Step Behavior

After running scenarios:
1. Results saved to `state.stress_scenarios`
2. Dashboard regenerated to embed stress data
3. Leaderboard regenerated to show stress column
4. Boards regenerated for consistency

## Key Implementation Files

- `modules/stress_scenarios.py`: Core stress testing logic
- `engine/runner.py`: `_step_stress_scenarios()` method
- `settings.py`: All STRESS_* configuration

---
*Step: 12*
*Category: Post-analysis*
*Gate: None (informational)*
