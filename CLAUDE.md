# EA Stress Test System v2

Stress-test MT5 Expert Advisors through a workflow designed to be driven by an LLM (Claude/Codex/etc) but runnable programmatically.

## Getting Started

1. Read `ROADMAP.md` for build status.
2. Read `HANDOFF.md` for stability/correctness notes and the current run state on this machine.
3. Run `python -m pytest -q` to verify the repo.

## System Overview

The system runs an MT5 EA through a gated workflow and produces dashboards + global indices.

| Step | Name | Gate | Notes |
|------|------|------|-------|
| 1 | Load EA | File exists | |
| 1B | Inject OnTester | Compiles | |
| 1C | Inject Safety | Compiles | Adds safety inputs if missing |
| 2 | Compile | No errors | If fails: `/mql5-fixer` |
| 3 | Extract Params | Params found | Workflow pauses here |
| 4 | Analyze Params | Ranges valid | LLM `/param-analyzer` output |
| 5 | Validate Trades | Trades >= `MIN_TRADES` | Uses "wide" params |
| 5B | Fix EA | Trades >= `MIN_TRADES` | LLM `/mql5-fixer` (max 3) |
| 6 | Create INI | INI valid | Uses optimization ranges |
| 7 | Run Optimization | Passes > 0 | Genetic optimization |
| 8 | Parse Results | Valid passes found | Filters by `MIN_TRADES` |
| 8B | Select Passes | Top N chosen | LLM or auto-score |
| 9 | Backtest Top Passes | Gates | Backtests selected passes |
| 10 | Monte Carlo | Gates | Robustness simulation |
| 11 | Generate Reports | N/A | Dashboard + leaderboard + boards |
| 12 | Stress Scenarios | N/A | Tick vs OHLC windows + overlays |
| 13 | Forward Windows | N/A | Time slices from best-pass trades |
| 14 | Multi-Pair (optional) | N/A | Same EA, multiple symbols |

Outputs:
- Dashboard: `runs/dashboards/<workflow_id>/index.html`
- Leaderboard: `runs/leaderboard/index.html`
- Boards: `runs/boards/index.html`

## UI Notes

- All tables are sortable: click any column header (Leaderboard, Boards, and the Dashboard pass/stress/forward tables).
- Leaderboard `Stress` column is populated only for the workflow's stress-tested pass (see cell tooltip for details).
- Boards workflow rows fall back to Step 5 validation metrics when a workflow fails later and `state.metrics` is missing/empty.
- Dashboard includes navigation buttons to `Boards` and `Leaderboard`.

## Key stability principles (avoid flaky runs)

1. **Deterministic report names**: MT5 writes into shared folders; report collisions are the #1 root cause of "wrong run shown".
2. **Deterministic report selection**: Never "pick newest file".
3. **Progress logging**: long MT5 runs emit periodic "still running" messages to avoid silent hangs.
4. **Post-step report refresh**: dashboards embed JSON at generation time; post-steps refresh reports so stress/forward results actually appear.

## Step 4: Parameter Analysis (LLM output contract)

Step 4 must produce two artifacts:

1. `wide_validation_params` (maximize trades so Step 5 can confirm the EA actually trades)
2. `optimization_ranges` (ranges/fixed params for optimization)

Programmatic usage:
```python
from engine.runner import WorkflowRunner

runner = WorkflowRunner("C:/path/to/EA.mq5", symbol="GBPUSD", timeframe="H1", auto_stats_analysis=True)
runner.run(pause_for_analysis=True)  # pauses after Step 3
runner.continue_with_params(wide_validation_params, optimization_ranges)
```

Important:
- The runner automatically forces injected safety params to loose values for validation and fixed values for optimization/backtests.
- The runner also carries forward missing `Use_*` / `Enable_*` boolean toggles from `wide_validation_params` into the optimization INI as fixed params. This prevents "0 trades everywhere" optimizations when a trade-enabling toggle was omitted from ranges.

## Step 8B: Selecting passes (LLM or auto-score)

You can select passes with an LLM (`/stats-analyzer`) or enable deterministic auto-selection:

- `auto_stats_analysis=True` when constructing `WorkflowRunner`, or
- `settings.AUTO_STATS_ANALYSIS = True`

Auto-selection picks top N passes by the same composite score used on the leaderboard (plus a small bonus for positive back+forward).

## Stress Scenarios (Step 12)

The dynamic suite runs windows anchored to workflow end date:
- Rolling days: `settings.STRESS_WINDOW_ROLLING_DAYS` (default includes 7/14/30/60/90)
- Calendar months: `settings.STRESS_WINDOW_CALENDAR_MONTHS_AGO` (default includes 1/2/3 months ago)
- Models per window: OHLC (1m) and Tick (`settings.STRESS_WINDOW_MODELS = [1, 0]`)
- Tick-only latency variants: `settings.STRESS_TICK_LATENCY_MS`
- Spread/slippage overlays are computed post-hoc from the trade list (`settings.STRESS_INCLUDE_OVERLAYS=True`)

Tick validation:
- In addition to MT5 "History Quality %", tick-model scenarios include a tick-file coverage check and surface it in UI.

## Tests

```bash
python -m pytest -q
```

## Task Tracking with Beads

This project uses beads for persistent, git-backed task tracking across agent sessions. See `AGENTS.md` for agent-specific instructions.
