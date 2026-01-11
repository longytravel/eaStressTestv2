# Architecture

**Analysis Date:** 2026-01-11

## Pattern Overview

**Overall:** Gated Workflow Engine with LLM Integration Points

**Key Characteristics:**
- 14-step sequential workflow with pass/fail gates
- State persistence between steps for recovery and auditing
- LLM pause points for parameter analysis and pass selection
- Deterministic report naming to avoid MT5 file collisions
- Modular step execution (each step is independent function)

## Layers

**Engine Layer:**
- Purpose: Workflow orchestration and state management
- Contains: `WorkflowRunner` class, `StateManager` class, gate checks
- Location: `engine/runner.py`, `engine/state.py`, `engine/gates.py`
- Depends on: Modules layer, settings
- Used by: Scripts, LLM skills

**Modules Layer:**
- Purpose: Individual workflow step implementations
- Contains: compiler, optimizer, backtest, monte_carlo, injector, params, etc.
- Location: `modules/*.py`
- Depends on: Settings, MT5 terminal (external)
- Used by: Engine layer (WorkflowRunner)

**Reports Layer:**
- Purpose: HTML dashboard and leaderboard generation
- Contains: Dashboard templates, leaderboard aggregation, boards view
- Location: `reports/*.py`, `reports/templates/`
- Depends on: Workflow state data
- Used by: Engine layer (Step 11)

**Reference Layer:**
- Purpose: MQL5 documentation lookup for LLM skills
- Contains: PDF indexer, lookup utilities
- Location: `reference/*.py`
- Depends on: `mql5.pdf`
- Used by: `/mql5-lookup` skill

**Scripts Layer:**
- Purpose: Entry points for running workflows
- Contains: Batch runners, cleanup utilities, continuation scripts
- Location: `scripts/*.py`
- Depends on: Engine layer
- Used by: User (command line)

## Data Flow

**Workflow Execution:**

1. User runs script or LLM invokes `/stress-test` skill
2. `WorkflowRunner.__init__()` creates `StateManager` with workflow ID
3. `run()` method executes steps 1-8 sequentially
4. **PAUSE at Step 3**: `awaiting_param_analysis` - LLM analyzes EA parameters
5. `continue_with_params()` resumes with wide params + optimization ranges
6. Steps 5-8 execute (validate trades, create INI, run optimization, parse results)
7. **PAUSE at Step 8**: `awaiting_stats_analysis` (unless `auto_stats_analysis=True`)
8. LLM or auto-scorer selects top 20 passes
9. `continue_with_selected_passes()` runs Steps 9-14
10. Dashboard generated, workflow marked complete

**State Management:**
- JSON file per workflow: `runs/workflow_{id}.json`
- Saved after each step completion
- Contains: step results, metrics, gates, errors, checkpoints
- Recovery: `StateManager.load(workflow_id)` or `WorkflowRunner.from_workflow_id()`

## Key Abstractions

**WorkflowRunner:**
- Purpose: Orchestrate the 14-step workflow
- Location: `engine/runner.py`
- Pattern: Stateful controller with explicit pause/resume points
- Methods: `run()`, `continue_with_params()`, `continue_with_selected_passes()`

**StateManager:**
- Purpose: Persist workflow state to JSON
- Location: `engine/state.py`
- Pattern: Repository with step tracking
- Key fields: `steps`, `metrics`, `gates`, `checkpoints`

**Gates:**
- Purpose: Pass/fail validation for each step
- Location: `engine/gates.py`
- Pattern: Pure functions returning `(passed, result_dict)`
- Examples: `check_profit_factor()`, `check_min_trades()`, `check_monte_carlo()`

## Entry Points

**WorkflowRunner:**
- Location: `engine/runner.py`
- Triggers: Script instantiation, `/stress-test` skill
- Responsibilities: Initialize state, execute steps, manage pauses

**Scripts:**
- Location: `scripts/*.py`
- Triggers: User command line execution
- Examples: `scripts/run_gbpusd.py`, `scripts/continue_workflow.py`

## Error Handling

**Strategy:** Exception capture with state persistence

**Patterns:**
- Each step wrapped: try/catch, error stored in `state.errors[]`
- Step marked as `failed`, workflow status updated
- Recovery: Fix issue, reload state, resume from failed step
- MT5 process cleanup: `_terminate_terminal_processes()` on timeout

## Cross-Cutting Concerns

**Logging:**
- `on_progress` callback for progress messages
- Print statements to console
- Step results persisted in state JSON

**Validation:**
- Gate functions validate step outputs
- Threshold-based (MIN_TRADES, MIN_PROFIT_FACTOR, etc.)
- Configurable via `settings.py`

**Report Naming:**
- `_make_report_name()` generates deterministic, unique names
- Pattern: `{workflow_id}_{tag}_{extra}` with SHA1 hash truncation
- Prevents MT5 report collisions in shared folders

---

*Architecture analysis: 2026-01-11*
*Update when major patterns change*
