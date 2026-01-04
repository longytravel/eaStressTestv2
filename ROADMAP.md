# EA Stress Test System v2 - Build Roadmap

**Status:** Phase 14 complete (Determinism + Stress + Boards + Post-step refresh)  
**Last Updated:** 2026-01-04

See `HANDOFF.md` for stability/correctness notes and the current run state on this machine.

## Quick Reference

| Setting | Value |
|---------|-------|
| Backtest Period | 4 years (3 in-sample + 1 forward) |
| Data Model | 1-minute OHLC (plus tick validation in stress tests) |
| Execution Latency | 10ms (baseline) |
| Account | £3,000 GBP |
| Platform | MT5 |
| LLM | Claude/Codex/etc (model-agnostic) |

## Phase 1: Project Setup + Terminal Registry
- [x] `settings.py` baseline thresholds + run config
- [x] `terminals.json` terminal registry
- [x] `engine/terminals.py` selection + default terminal

## Phase 2: Core MT5 Modules
- [x] `modules/compiler.py` compile EA via MetaEditor
- [x] `modules/backtest.py` deterministic backtest runner + report parsing
- [x] `modules/optimizer.py` genetic optimization + XML parsing
- [x] `modules/monte_carlo.py` robustness simulation
- [x] `modules/params.py` extract EA inputs
- [x] `modules/injector.py` inject OnTester + safety guards

## Phase 3: Workflow Engine
- [x] `engine/state.py` persistent workflow state
- [x] `engine/gates.py` pass/fail gates + composite score
- [x] `engine/runner.py` orchestration (steps 1-14)

## Phase 4: Reporting/UI
- [x] `reports/workflow_dashboard.py` per-workflow dashboards
- [x] `reports/leaderboard.py` global leaderboard
- [x] `reports/boards.py` global workflows + scenarios (Boards)
- [x] Navigation: Dashboard -> Boards -> Leaderboard
- [x] Tables are sortable (click table headers)

## Phase 5: Claude Skills (optional orchestration)
- [x] `.claude/skills/*` parameter analysis, stats analysis, MQL5 fixer, EA improver

## Phase 10: Parameter Analysis (LLM-driven)
- [x] Workflow pauses after Step 3
- [x] `continue_with_params(wide_params, opt_ranges)` continues
- [x] No Python "param analyzer" heuristics in the runner (LLM output is the contract)
- [x] Runner carries forward missing `Use_*` / `Enable_*` toggles into optimization INIs when required for activity

## Phase 11: EA Fix Loop (when validation fails)
- [x] Step 5B pause + max 3 fix attempts
- [x] `backup_original_ea()` + `restart_after_fix()`

## Phase 12: Determinism + Stability
- [x] Deterministic per-workflow report names + deterministic report selection
- [x] Targeted cleanup of stale MT5 processes
- [x] Commission accounting fixed in trade extraction (equity/profit reconcile with MT5)

## Phase 13: Stress Scenarios + Boards
- [x] Stress windows: rolling days + calendar months
- [x] Models: OHLC (1m) + Tick
- [x] Latency variants (tick model)
- [x] Spread/slippage overlays (post-hoc)
- [x] Tick-file coverage detection + surfaced in Boards + Dashboard stress table

## Phase 14: Post-run Extensions
- [x] Forward-window slices (Step 13) from best-pass trades
- [x] Multi-pair workflow support (Step 14) integrated (off by default)
- [x] Post-step report refresh so stress/forward/multi-pair appear in dashboards/boards
- [x] Progress logging for long MT5 runs (avoid silent hangs)

## Future Work
- Full walk-forward testing module (re-optimize per rolling window).
- Pluggable LLM provider interface for Step 4 outputs (Claude/Codex/OpenAI/Anthropic).
