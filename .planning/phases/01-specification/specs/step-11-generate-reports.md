# Step 11: Generate Reports

**Status:** Always runs (even on earlier failures)
**Gate:** None (informational step)
**Input:** All workflow state from Steps 1-10

---

## Overview

Step 11 generates three report types:
1. **Dashboard:** Per-workflow interactive SPA with equity curves, metrics, charts
2. **Leaderboard:** Global ranking of best passes across all workflows
3. **Boards:** Workflow summary index with scenario results

**Key Principle:** This step ALWAYS runs, even when earlier steps fail. Failed workflows still get dashboards showing what went wrong.

---

## Three Report Types

### 1. Dashboard (`runs/dashboards/<workflow_id>/index.html`)

Per-workflow interactive dashboard showing:
- Top 20-50 passes with metrics
- Equity curves (in-sample + forward)
- Profit/drawdown scatter plot
- Monte Carlo results
- Gate status
- Stress scenario results (after Step 12)
- Forward windows (after Step 13)

### 2. Leaderboard (`runs/leaderboard/index.html`)

Global ranking of passes across ALL workflows:
- Sorted by Go Live Score
- Links to individual dashboards
- Stress test results (for stress-tested passes)
- Excludes failed/stuck workflows

### 3. Boards (`runs/boards/index.html`)

Workflow summary index:
- All workflows with key metrics
- Scenario results (stress tests, forward windows)
- Quick navigation to dashboards
- Desktop shortcut auto-created (Windows)

---

## Process

```python
# Code reference: engine/runner.py:1870-1933

def _step_generate_reports(self) -> tuple[bool, dict]:
    """Step 11: Generate dashboard and update leaderboard."""
    from reports.workflow_dashboard import generate_dashboard_from_workflow
    from reports.leaderboard import generate_leaderboard
    from reports.boards import generate_boards

    # Calculate composite score
    score = gates.calculate_composite_score(self.state.get('metrics', {}))
    self.state.set('composite_score', score)

    # Check go-live readiness
    go_live = gates.check_go_live_ready(self.state.to_dict())
    self.state.set('go_live', go_live)

    # Generate failure diagnosis if needed
    if not go_live['go_live_ready']:
        diagnoses = gates.diagnose_failure(
            self.state.get('gates', {}),
            self.state.get('metrics', {}),
        )
        self.state.set('diagnoses', diagnoses)

    # Save state before generating reports
    self.state.save()

    # Generate all three report types
    dashboard_path = generate_dashboard_from_workflow(str(self.state.state_file), ...)
    leaderboard_path = generate_leaderboard(open_browser=False)
    boards_path = generate_boards(open_browser=False)
```

---

## Dashboard Generation

### Function Signature

```python
# Code reference: reports/workflow_dashboard.py:59-132

def generate_dashboard_from_workflow(
    workflow_path: str,
    output_dir: Optional[str] = None,   # Default: runs/dashboards/{workflow_id}
    open_browser: bool = False,
    run_backtests: bool = False,        # Slow mode: run backtests for equity curves
    top_n: int = 20,                    # Passes to display
) -> str:
```

### Data Sources (Priority Order)

1. **Step 9 backtest results** (preferred - actual backtests, equity curves)
2. **Step 7 optimization results** (fallback - optimization-only metrics)

```python
# Code reference: reports/workflow_dashboard.py:156-167

# Check for step 9 backtest results first (preferred - more accurate)
bt_step = steps.get('9_backtest_robust', {})
bt_result = bt_step.get('result', {})
backtest_results = bt_result.get('all_results', [])

if backtest_results:
    return _prepare_data_from_backtests(state, backtest_results)

# Fall back to optimization results
opt_step = steps.get('7_run_optimization', {})
```

### Dashboard Data Structure

```python
# Code reference: reports/workflow_dashboard.py:303-336, 595-630

data = {
    'ea_name': str,
    'symbol': str,
    'timeframe': str,
    'from_date': str,              # Backtest start
    'to_date': str,                # Backtest end
    'forward_date': str,           # In-sample/forward split
    'stress_scenarios': dict,      # From Step 12
    'forward_windows': dict,       # From Step 13
    'ea_inputs': list,             # EA parameters from Step 3
    'optimization': {
        'total_passes': int,
        'valid_passes': int,
        'consistent_passes': int,
        'rejected': dict,
        'scatter': list,           # In-sample vs forward scatter data
        'insights': list,
    },
    'pass_list': list[int],        # Ordered list of pass numbers
    'passes': {                    # Keyed by pass number
        '123': {
            'success': bool,
            'pass': int,
            'parameters': dict,
            'opt': {'in_profit': float, 'fwd_profit': float},
            'bt': {                # Backtest metrics
                'total_trades': int,
                'net_profit': float,
                'profit_factor': float,
                'max_drawdown_pct': float,
                'sharpe_ratio': float,
                'recovery_factor': float,
                'win_rate': float,
                'expected_payoff': float,
                'data_quality': {...},
                'split': {
                    'in_sample': {'net_profit': float, 'trades': int},
                    'forward': {'net_profit': float, 'trades': int},
                },
            },
            'advanced': {...},     # Z-score, AHPR, GHPR, LR
            'drawdown': {...},
            'streaks': {...},
            'positions': {...},
            'holding_times': {...},
            'costs': {...},
            'direction': {...},
            'charts': {...},       # Histogram, MFE/MAE data
            'equity': {
                'in_sample': list[float],
                'forward': list[float],
            },
            'monte_carlo': {...},
        },
    },
    'selected_pass': int,          # First pass (best)
    'claude_analysis': str,        # LLM analysis if available
    'gates': dict,                 # All gate results
    'safety': {
        'max_spread_pips': float,
        'max_slippage_pips': float,
    },
    'thresholds': {
        'min_trades': 50,
        'min_profit_factor': 1.5,
        'max_drawdown_pct': 30.0,
        'min_mc_confidence': 70,
        'max_ruin_probability': 5,
    },
}
```

### Output Files

```
runs/dashboards/<workflow_id>/
├── index.html      # Interactive SPA dashboard
└── data.json       # Raw JSON data for debugging/API
```

---

## Leaderboard Generation

### Function Signature

```python
# Code reference: reports/leaderboard.py:32-90

def generate_leaderboard(
    runs_dir: str = "runs",
    output_dir: Optional[str] = None,   # Default: runs/leaderboard
    open_browser: bool = False,
    passes_per_workflow: int = 30,      # TOP_PASSES_BACKTEST
) -> str:
```

### Data Collection

```python
# Code reference: reports/leaderboard.py:43-63

EXCLUDED_STATUSES = {'failed', 'awaiting_param_analysis', 'awaiting_stats_analysis', 'awaiting_ea_fix', 'pending'}

for state_file in sorted(runs_path.glob("workflow_*.json")):
    state = json.loads(state_file.read_text())

    # Skip failed/stuck workflows
    if state.get("status") in EXCLUDED_STATUSES:
        continue

    passes = extract_top_passes(state, state_file, top_n=passes_per_workflow)
    all_passes.extend(passes)
```

### Leaderboard Row Structure

```python
# Code reference: reports/leaderboard.py:285-311

row = {
    'ea_name': str,
    'symbol': str,
    'timeframe': str,
    'workflow_id': str,
    'created_at': str,
    'pass_num': int,
    'dashboard_link': str,
    'score': str,                  # "7.2" formatted
    'score_num': float,            # For sorting
    'profit': str,                 # "£2,500" formatted
    'profit_num': float,
    'stress_worst_profit': str,    # Worst stress scenario result
    'stress_worst_profit_num': float,
    'stress_worst_scenario': str,  # Which scenario was worst
    'profit_factor': str,
    'pf_num': float,
    'max_drawdown_pct': str,
    'dd_num': float,
    'total_trades': int,
    'win_rate': str,
    'win_rate_num': float,
    'forward_result': str,
    'forward_num': float,
    'back_result': str,
    'back_num': float,
    'status': str,                 # 'consistent', 'forward_only', 'back_only', 'mixed'
    'status_label': str,           # '✓ Consistent', '↗ Forward Only', etc.
    'rank': int,                   # Global ranking
}
```

### Stress Scenario Integration

```python
# Code reference: reports/leaderboard.py:213-238

# Stress results are only shown for the stress-tested pass
if pass_num == stress_pass_num and worst_profit is not None:
    stress_worst_profit = _fmt_gbp(worst_profit)
    stress_worst_scenario = worst_label
else:
    stress_worst_scenario = f"Stress scenarios were run for Pass #{stress_pass_num} only"
```

### Output Files

```
runs/leaderboard/
├── index.html      # Interactive SPA leaderboard
└── data.json       # Raw JSON data
```

---

## Boards Generation

### Function Signature

```python
# Code reference: reports/boards.py:170-357

def generate_boards(
    runs_dir: str = "runs",
    output_dir: Optional[str] = None,   # Default: runs/boards
    open_browser: bool = False,
) -> str:
```

### Workflow Row Structure

```python
# Code reference: reports/boards.py:214-235

workflow = {
    'workflow_id': str,
    'ea_name': str,
    'symbol': str,
    'timeframe': str,
    'created_at': str,
    'created_at_fmt': str,         # "Jan 6, 09:18"
    'status': str,
    'notes': str,                  # Auto-generated feature summary
    'score_num': float,            # Go Live Score
    'profit_num': float,
    'pf_num': float,
    'dd_num': float,
    'trades_num': int,
    'win_rate_num': float,
    'forward_num': float,
    'back_num': float,
    'go_live_ready': bool,
    'dashboard_link': str,
}
```

### Scenario Row Structure

```python
# Code reference: reports/boards.py:245-276

scenario = {
    'workflow_id': str,
    'ea_name': str,
    'symbol': str,
    'timeframe': str,
    'scenario_id': str,
    'scenario_label': str,
    'success': bool,
    'variant': str,                # 'base', 'tick', 'latency', 'overlay', 'forward_window'
    'tags': list,
    'window_id': str,
    'window_label': str,
    'from_date': str,
    'to_date': str,
    'model': int,
    'execution_latency_ms': int,
    'spread_points': int,
    'overlay_spread_pips': float,
    'overlay_slippage_pips': float,
    'profit_num': float,
    'pf_num': float,
    'dd_num': float,
    'trades_num': int,
    'hq_num': float,               # History quality %
    'tick_files_ok': int,
    'tick_files_missing': list,
    'errors': list,
}
```

### Fallback Metrics

```python
# Code reference: reports/boards.py:107-167

def _best_workflow_metrics(state: dict) -> dict:
    """Get metrics from the best pass for Go Live Score calculation."""

    # Priority 1: Best optimization pass (most accurate)
    # Priority 2: Backtest results
    # Priority 3: Explicit metrics field
    # Priority 4: Step 5 validation result (fallback for early-stage workflows)
```

**Important:** Boards fall back to Step 5 validation metrics when a workflow fails later and `state.metrics` is empty. This ensures every workflow shows some metrics.

### Auto-Notes Generation

```python
# Code reference: reports/boards.py:43-104

def _generate_notes(state: dict) -> str:
    """Generate a short note summarizing key workflow characteristics."""
    # Examples:
    # "3 params | London 1.5x"
    # "5 params | Asymmetric + BE + Trail"
    # "2 params | stress tested"
```

### Desktop Shortcut (Windows)

```python
# Code reference: reports/boards.py:340-350

# Convenience: keep a Desktop shortcut up to date on Windows
if sys.platform.startswith("win"):
    desktop = Path(os.path.expanduser("~")) / "Desktop"
    shortcut = desktop / "EA Stress Test Boards.url"
    shortcut.write_text(f"[InternetShortcut]\nURL={output_path.resolve().as_uri()}\n")
```

### Output Files

```
runs/boards/
├── index.html      # Interactive SPA boards
└── data.json       # Raw JSON data
```

---

## Post-Step Dashboard Refresh

**Critical:** Dashboards embed JSON data at generation time. After Steps 12 (stress) and 13 (forward windows), the dashboard must be **refreshed** to show new results.

```python
# Code reference: From stress_scenarios and forward_windows steps

# After Step 12 or 13 completes, refresh dashboard:
generate_dashboard_from_workflow(str(self.state.state_file), ...)
```

This is handled automatically by the runner after post-steps complete.

---

## Output Paths Summary

| Report | Path | Updated When |
|--------|------|--------------|
| Dashboard | `runs/dashboards/<workflow_id>/index.html` | Step 11, after Step 12, after Step 13 |
| Leaderboard | `runs/leaderboard/index.html` | Every Step 11 (aggregates all workflows) |
| Boards | `runs/boards/index.html` | Every Step 11 (aggregates all workflows) |

---

## Go-Live Readiness Check

```python
# Code reference: engine/gates.py:286-316

def check_go_live_ready(state: dict) -> dict:
    """Final check: Is the EA ready for live trading?"""
    critical_gates = [
        'profit_factor',
        'max_drawdown',
        'minimum_trades',
        'mc_confidence',
        'mc_ruin',
    ]

    all_passed = all(gates[g].get('passed', False) for g in critical_gates)

    return {
        'go_live_ready': all_passed,
        'gate_results': {g: passed for g, passed in ...},
        'message': 'READY for go-live' if all_passed else 'NOT ready - some gates failed',
    }
```

---

## Failure Diagnosis

When go-live check fails, diagnoses are generated:

```python
# Code reference: engine/gates.py:417-474

def diagnose_failure(gates: dict, metrics: dict) -> list[str]:
    """Provide failure diagnosis explaining WHY gates failed."""

    # Example diagnoses:
    # "PF 1.2 < 1.5: Average win ($45) is too close to average loss ($42). Consider tightening stop loss."
    # "Drawdown 35% > 30%: Consider adding position sizing, trailing stops."
    # "Only 30 trades (need 50+): EA may be too selective. Consider widening entry conditions."
    # "MC confidence 65% < 70%: Results may be due to luck."
    # "Ruin probability 8% > 5%: High risk of account blowup."
```

---

## UI Notes (from CLAUDE.md)

- **All tables sortable:** Click column header (Leaderboard, Boards, Dashboard pass/stress/forward tables)
- **Leaderboard Stress column:** Populated only for the workflow's stress-tested pass (see cell tooltip)
- **Boards fallback:** Shows Step 5 validation metrics when workflow fails later and metrics missing
- **Dashboard navigation:** Includes buttons to Boards and Leaderboard

---

## Settings Reference

```python
# Code reference: settings.py

# Report paths
RUNS_DIR = "runs"
DASHBOARDS_DIR = "runs/dashboards"
LEADERBOARD_DIR = "runs/leaderboard"

# Display settings
TOP_PASSES_DISPLAY = 20     # Passes shown in dashboard
TOP_PASSES_BACKTEST = 30    # Passes included in leaderboard
```

---

## Implementation Notes

### Code References
- `engine/runner.py:1870-1933` — `_step_generate_reports()` method
- `reports/workflow_dashboard.py` — Dashboard generation
- `reports/leaderboard.py` — Leaderboard generation
- `reports/boards.py` — Boards generation
- `engine/gates.py:286-316` — `check_go_live_ready()`
- `engine/gates.py:417-474` — `diagnose_failure()`

### Template Location

```
reports/templates/
├── dashboard_spa.html      # Dashboard template
├── leaderboard_spa.html    # Leaderboard template
└── boards_spa.html         # Boards template
```

### Always-Run Guarantee

Step 11 is the only step that always runs regardless of earlier failures. This ensures:
- Failed workflows still get a dashboard showing what went wrong
- Leaderboard/boards always reflect current state
- Users can always find their workflow results

---

*Spec version: 1.0*
*Last updated: 2026-01-11*
