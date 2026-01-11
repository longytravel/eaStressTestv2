# Step 13: Forward Windows Specification

## Overview

Step 13 slices the best-pass trade list into time windows to analyze performance across different periods. Unlike Step 12 (which runs new backtests), this step computes metrics directly from existing trade data.

**Gate**: None (informational step, does not fail the workflow)
**Auto-run**: Controlled by `settings.AUTO_RUN_FORWARD_WINDOWS` (default: True)
**Runs after**: Step 12 (Stress Scenarios) or Step 11 if stress is disabled

## Purpose

1. Decompose total performance into time-based segments
2. Compare in-sample vs forward (out-of-sample) periods
3. Identify yearly and monthly performance patterns
4. Provide recent performance windows matching stress scenarios

## Input

From workflow state:
- `backtest_results.report_path`: HTML report from best pass (Step 9)
- `backtest_results.pass_num`: Pass number for reference
- `backtest_dates`: Workflow date range with start, end, and split dates

## Window Types

All windows are computed by filtering the trade list by close time.

### Segment Windows

| Window ID | Label | Boundaries | Kind |
|-----------|-------|------------|------|
| `full` | Full period | `start_date` to `end_date` | `full` |
| `in_sample` | In-sample | `start_date` to `split_date` | `segment` |
| `forward` | Forward | `split_date` to `end_date` | `segment` |

The split date comes from `settings.FORWARD_YEARS` (default: 1 year).

### Rolling Windows (reuses stress settings)

Uses `settings.STRESS_WINDOW_ROLLING_DAYS` (default: `[7, 14, 30, 60, 90]`)

| Window ID | Label | Calculation | Kind |
|-----------|-------|-------------|------|
| `last_7d` | Last 7 days | `end_date - 7 days` to `end_date` | `rolling` |
| `last_14d` | Last 14 days | `end_date - 14 days` to `end_date` | `rolling` |
| `last_30d` | Last 30 days | `end_date - 30 days` to `end_date` | `rolling` |
| `last_60d` | Last 60 days | `end_date - 60 days` to `end_date` | `rolling` |
| `last_90d` | Last 90 days | `end_date - 90 days` to `end_date` | `rolling` |

### Calendar Month Windows (reuses stress settings)

Uses `settings.STRESS_WINDOW_CALENDAR_MONTHS_AGO` (default: `[1, 2, 3]`)

| Window ID | Label | Calculation | Kind |
|-----------|-------|-------------|------|
| `month_2025_12` | Dec 2025 | First to last day of month | `calendar` |
| `month_2025_11` | Nov 2025 | First to last day of month | `calendar` |
| `month_2025_10` | Oct 2025 | First to last day of month | `calendar` |

### Yearly Windows

Automatically generated for each year in the backtest range.

| Window ID | Label | Boundaries | Kind |
|-----------|-------|------------|------|
| `year_2022` | Year 2022 | Jan 1 to Dec 31 (clamped to range) | `year` |
| `year_2023` | Year 2023 | Jan 1 to Dec 31 (clamped to range) | `year` |
| `year_2024` | Year 2024 | Jan 1 to Dec 31 (clamped to range) | `year` |
| `year_2025` | Year 2025 | Jan 1 to Dec 31 (clamped to range) | `year` |

## Metrics Computation

For each window, metrics are computed from the filtered trade list:

### Algorithm

```python
def _metrics_for_window(window_start, window_end):
    # Calculate starting balance at window_start
    balance = initial_balance
    for trade in sorted_trades:
        if trade.close_time < window_start:
            balance += trade.net_profit
        else:
            break

    start_balance = balance
    peak = start_balance
    max_dd = 0.0

    profit = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    wins = 0
    total = 0

    for trade in sorted_trades:
        if trade.close_time < window_start:
            continue
        if trade.close_time > window_end:
            break

        p = trade.net_profit
        total += 1
        profit += p

        if p > 0:
            wins += 1
            gross_profit += p
        elif p < 0:
            gross_loss += abs(p)

        # Update drawdown
        balance += p
        if balance > peak:
            peak = balance
        if peak > 0:
            dd = (peak - balance) / peak
            if dd > max_dd:
                max_dd = dd

    # Calculate profit factor
    if gross_loss <= 0:
        pf = 99.0 if gross_profit > 0 else 0.0
    else:
        pf = gross_profit / gross_loss

    win_rate = (wins / total * 100.0) if total > 0 else 0.0

    return {
        "profit": profit,
        "profit_factor": pf,
        "max_drawdown_pct": max_dd * 100.0,
        "total_trades": total,
        "win_rate": win_rate,
    }
```

### Key Points

1. **Starting Balance**: The balance at window start accounts for all prior trades, making drawdown calculations realistic.

2. **Trade Selection**: Trades are filtered by `close_time`, not `open_time`.

3. **Drawdown**: Calculated relative to the running peak within the window.

4. **Profit Factor**: Capped at 99.0 when there are no losses.

## Output Structure

```python
{
    "success": True,
    "pass_num": 42,
    "report_path": "path/to/best_pass.html",
    "history_quality_pct": 99.5,
    "model": 1,  # From Step 9 backtest
    "window_count": 15,
    "windows": [
        {
            "id": "full",
            "label": "Full period",
            "kind": "full",
            "from_date": "2022.01.11",
            "to_date": "2026.01.11",
            "metrics": {
                "profit": 2500.0,
                "profit_factor": 2.1,
                "max_drawdown_pct": 12.5,
                "total_trades": 150,
                "win_rate": 55.0,
            }
        },
        {
            "id": "in_sample",
            "label": "In-sample",
            "kind": "segment",
            "from_date": "2022.01.11",
            "to_date": "2025.01.11",
            "metrics": {
                "profit": 1800.0,
                "profit_factor": 2.0,
                "max_drawdown_pct": 11.0,
                "total_trades": 120,
                "win_rate": 54.0,
            }
        },
        {
            "id": "forward",
            "label": "Forward",
            "kind": "segment",
            "from_date": "2025.01.11",
            "to_date": "2026.01.11",
            "metrics": {
                "profit": 700.0,
                "profit_factor": 2.3,
                "max_drawdown_pct": 8.0,
                "total_trades": 30,
                "win_rate": 58.0,
            }
        },
        {
            "id": "last_30d",
            "label": "Last 30 days",
            "kind": "rolling",
            "from_date": "2025.12.12",
            "to_date": "2026.01.11",
            "metrics": {
                "profit": 150.0,
                "profit_factor": 2.5,
                "max_drawdown_pct": 3.5,
                "total_trades": 8,
                "win_rate": 62.5,
            }
        },
        {
            "id": "year_2025",
            "label": "Year 2025",
            "kind": "year",
            "from_date": "2025.01.01",
            "to_date": "2025.12.31",
            "metrics": {
                "profit": 850.0,
                "profit_factor": 2.2,
                "max_drawdown_pct": 9.0,
                "total_trades": 45,
                "win_rate": 56.0,
            }
        },
        # ... more windows
    ]
}
```

## Dashboard Display

Forward window results appear in the dashboard as:
1. A dedicated "Forward Windows" table
2. Sortable by any column
3. Color-coded by window kind (segment, rolling, calendar, year)
4. Key comparison: In-sample vs Forward for overfitting detection

### Overfitting Indicators

The dashboard highlights:
- Forward profit significantly lower than in-sample: possible overfitting
- Forward profit factor collapse: edge may be curve-fitted
- Consistent yearly performance: robust strategy

## Skip Conditions

Step 13 is skipped when:
- No best-pass report available (Step 9 failed)
- Trade extraction fails

Skipped output:
```python
{
    "success": True,
    "skipped": True,
    "reason": "No best-pass report available for forward windows"
}
```

## Error Handling

If trade extraction fails:
```python
{
    "success": False,
    "pass_num": 42,
    "report_path": "path/to/report.html",
    "error": "Failed to extract trades for forward windows"
}
```

## Post-Step Behavior

After computing windows:
1. Results saved to `state.forward_windows`
2. Dashboard regenerated to show forward window table
3. Boards regenerated for consistency

## Settings Reference

| Setting | Default | Usage in Step 13 |
|---------|---------|------------------|
| `BACKTEST_YEARS` | `4` | Total backtest period |
| `IN_SAMPLE_YEARS` | `3` | In-sample portion |
| `FORWARD_YEARS` | `1` | Forward (OOS) portion |
| `STRESS_WINDOW_ROLLING_DAYS` | `[7, 14, 30, 60, 90]` | Rolling window sizes |
| `STRESS_WINDOW_CALENDAR_MONTHS_AGO` | `[1, 2, 3]` | Calendar month offsets |
| `AUTO_RUN_FORWARD_WINDOWS` | `True` | Auto-run after reports |
| `DEPOSIT` | `3000` | Initial balance for calculations |

## Key Implementation Files

- `engine/runner.py`: `_step_forward_windows()` method
- `modules/trade_extractor.py`: Trade list extraction from HTML reports

## Comparison: Step 12 vs Step 13

| Aspect | Step 12 (Stress) | Step 13 (Forward Windows) |
|--------|------------------|---------------------------|
| Execution | Runs MT5 backtests | Computes from trade list |
| Purpose | Test execution conditions | Analyze time periods |
| Model variants | Yes (OHLC, Tick) | No (uses existing data) |
| Cost overlays | Yes | No |
| Speed | Slow (many backtests) | Fast (trade filtering) |
| Windows | Rolling, Calendar | Rolling, Calendar, Yearly, Segments |

---
*Step: 13*
*Category: Post-analysis*
*Gate: None (informational)*
