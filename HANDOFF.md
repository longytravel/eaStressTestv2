# EA Stress Test v2 - Handoff Notes (2026-01-04)

This document is for a developer taking over this repo. It summarizes architecture, key stability/correctness work, and the current run state on this machine.

## What this system does

Runs a repeatable MT5 EA workflow:
- compile -> parameter extraction -> optimization -> backtest top passes -> Monte Carlo -> reports

Post-run extensions:
- Step 12: Stress scenarios (spread/slippage overlays, latency variants, rolling windows, tick vs OHLC comparisons)
- Step 13: Forward windows (time slices)
- Step 14 (optional): Re-run the full workflow on additional symbols

Outputs:
- Per-workflow dashboard: `runs/dashboards/<workflow_id>/index.html`
- Global leaderboard: `runs/leaderboard/index.html`
- Global boards (workflows + scenarios): `runs/boards/index.html`

Workflow state is persisted in `runs/workflow_<workflow_id>.json`. Large artifacts live in `runs/<workflow_id>/` (e.g., `optimization.json`, `backtests.json`).

## Snapshot (this machine)

The repo and MT5 terminal were cleaned to a fresh slate (archived, not deleted). A new unattended batch run was started for RSI Divergence Pro across 6 pairs.

- Desktop shortcuts:
  - `C:\\Users\\User\\Desktop\\EA Stress Boards.url`
  - `C:\\Users\\User\\Desktop\\EA Stress Leaderboard.url`
- Batch logs + PID: `runs/batch/` (`*.out.log`, `*.err.log`, `*.pid`)
- Archived prior runs: `archive/runs_*/`
- Archived MT5 cleanup: `<data_path>/ea_stress_cleanup_*/`

## Key repo entry points

- Workflow orchestrator: `engine/runner.py` (`WorkflowRunner`)
- Terminal config: `terminals.json` (MT5 `terminal64.exe` path + `data_path`)
- Core modules: `modules/compiler.py`, `modules/backtest.py`, `modules/optimizer.py`, `modules/monte_carlo.py`
- MT5 parsing + trade extraction: `modules/backtest.py`, `modules/trade_extractor.py`
- Stress scenarios + tick-file validation: `modules/stress_scenarios.py`
- Reporting/UI: `reports/workflow_dashboard.py`, `reports/leaderboard.py`, `reports/boards.py`

## Stability + correctness highlights

### 1) MT5 report collisions (root cause of "wrong run shown")

MT5 writes reports into shared folders. If report names collide, runs overwrite each other and dashboards read the wrong report.

Fixes:
- Deterministic per-workflow report names (`engine/runner.py`)
- Deterministic report selection when a `report_name` is provided (avoid "pick newest file")

### 2) Commission accounting (math audit)

Trade extraction allocates entry commission (and handles partial closes) so:
- `sum(trade.net_profit)` matches MT5 "Total Net Profit"
- equity curves match MT5 balance progression

Primary logic: `modules/trade_extractor.py`. Tests: `tests/test_trade_extractor.py`.

### 3) Post-step reports refresh (stress/forward results actually appear)

Dashboards embed JSON at generation time; post-steps update workflow JSON after the initial dashboard.

Fix:
- The runner refreshes dashboard/leaderboard/boards after post-steps

### 4) Tick "History Quality %" is not enough (real tick file coverage)

MT5 can show 100% "History Quality" even if it synthesizes ticks. The system checks for real tick files:

`<data_path>/bases/<server>/ticks/<SYMBOL>/YYYYMM.tkc`

Surfaced in UI:
- Boards scenario list `Tick Files`
- Dashboard stress table `Tick Files`

## Why RSI Divergence Pro had "no optimization results" on H4 (and the fix)

Symptom: default EA inputs produced 0 trades in the test window, so optimization yielded 0-trade passes.

Fix: carry trade-enabling toggles from validation into optimization (fixed params), e.g. slope filters disabled when needed for activity.

## Starting an unattended 6-pair run

```bash
python -u scripts/batch_run_rsi.py --symbols GBPUSD,EURUSD,USDJPY,AUDUSD,USDCAD,USDCHF --iterations 1 --stress --forward
```

Notes:
- The profile `reference/rsi_divergence_pro_profile.json` defines validation defaults and optimization ranges; it does not reuse previous optimized results.
- Progress logs stream via the runner `on_progress` callback into stdout.

## Cleanup (archive, don't delete)

```bash
python scripts/clean_slate.py --archive --yes
python scripts/mt5_cleanup.py --keep-ea RSI_Divergence_Pro --keep-core-only --archive --yes
```

## ISSUES RESOLVED (2026-01-11)

### Issue 1: Optimization Profit Not Reflected in Final Results - **BUG FOUND AND FIXED**

**Symptom:** Optimization shows £14,847 profit (315 trades), but final metrics show only £718 profit (59 trades).

**Root Cause (ACTUALLY A BUG):**
The composite score calculation was missing 70% of the formula!

The `score_metrics` dict was only passing:
- profit_factor (15% weight)
- max_drawdown (15% weight)

But was MISSING:
- **profit (25% weight)** - NOT passed!
- **total_trades (20% weight)** - NOT passed!
- **forward_result + back_result (25% weight)** - NOT passed!

This caused Pass 1414 (£719, 59 trades) to be ranked higher than Pass 9525 (£1,626, 328 trades).

**Correct Rankings (with full formula):**
| Pass | OLD Score | NEW Score | Profit | Trades |
|------|-----------|-----------|--------|--------|
| 9525 | 2.30 | **5.1** | £1,626 | 328 | ← Should have been selected
| 4205 | 2.90 | **4.6** | £1,659 | 107 |
| 1414 | 3.10 | 3.6 | £719 | 59 | ← Was incorrectly selected

**Fix Applied (2026-01-11):**
- Fixed `_step_backtest_robust()` - now passes all required fields to `calculate_composite_score()`
- Fixed `_auto_select_passes()` - same fix for auto mode

### Issue 2: Two-Stage Optimization Process Not Enforced - FIXED

**Symptom:** Workflow ran straight through Steps 8→8B→9 without pausing for re-optimization analysis.

**Root Cause:**
- `auto_stats_analysis=True` bypassed the mandatory `run_reopt_analysis()` call
- User was never shown toggle analysis or asked about re-optimization

**Fix Applied (2026-01-11):**
1. Modified `engine/runner.py` to run `run_reopt_analysis()` BEFORE auto-selecting passes
2. Added enforcement in `continue_with_analysis()` that requires `reopt_analysis_completed=True`
3. Added `skip_reopt_check=True` parameter for auto mode (after it runs analysis itself)
4. Error message explains the two-stage process if enforcement fails

**Enforcement Now Works:**
- Manual mode: `continue_with_analysis()` raises error if `run_reopt_analysis()` not called
- Auto mode: `run_reopt_analysis()` runs automatically before pass selection

**Reference Analysis from 2026-01-11 Run:**
Top 100 passes showed 100% consistency on 14 toggles:
- TRUE: Enable_Hidden_Divergence, Enable_Regular_Divergence, Enable_Asymmetric_Params, Enable_Session_Sizing, Use_Trading_Hours, Avoid_Friday_Close, Enable_Breakeven, Enable_Partial_Close
- FALSE: Use_Price_Slope_Filter, Use_RSI_Slope_Filter, Enable_RSI_Level_Filter, Enable_Momentum_Confirm, Enable_MA_Filter, Enable_Trailing

These patterns should have triggered a Stage 2 re-optimization with fixed toggles and narrowed ranges.

## Tests

```bash
python -m pytest -q
```
