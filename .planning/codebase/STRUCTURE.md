# Codebase Structure

**Analysis Date:** 2026-01-11

## Directory Layout

```
ea-stress-test-v2/
├── engine/             # Workflow orchestration
│   ├── runner.py       # WorkflowRunner class (main orchestrator)
│   ├── state.py        # StateManager (persistence)
│   ├── gates.py        # Pass/fail gate functions
│   └── terminals.py    # MT5 terminal registry
├── modules/            # Step implementations
│   ├── backtest.py     # Run backtests
│   ├── compiler.py     # Compile EAs
│   ├── injector.py     # Inject OnTester/safety
│   ├── loader.py       # Dynamic module loading
│   ├── monte_carlo.py  # Monte Carlo simulation
│   ├── optimizer.py    # Run optimization
│   ├── params.py       # Extract EA parameters
│   ├── pass_analyzer.py    # Analyze optimization passes
│   ├── reopt_analyzer.py   # Re-optimization recommendations
│   ├── stats_analyzer.py   # Statistics analysis
│   ├── stress_scenarios.py # Stress testing scenarios
│   └── trade_extractor.py  # Extract trades from reports
├── reports/            # Dashboard generation
│   ├── boards.py       # Boards view (all workflows)
│   ├── dashboard.py    # Per-workflow dashboard
│   ├── leaderboard.py  # Cross-workflow ranking
│   ├── pass_backtest.py    # Pass backtest reports
│   ├── stats_schema.py     # Stats JSON schema
│   ├── workflow_dashboard.py   # Main dashboard generator
│   └── templates/      # HTML templates
├── reference/          # MQL5 documentation
│   ├── lookup.py       # PDF lookup utilities
│   ├── mql5_indexer.py # PDF indexer
│   └── cache/          # Index cache (generated)
├── tests/              # Test suite
│   ├── conftest.py     # Pytest fixtures
│   └── test_*.py       # Test files
├── scripts/            # Entry point scripts
│   ├── clean_slate.py  # Reset runs directory
│   ├── mt5_cleanup.py  # Kill stuck MT5 processes
│   ├── batch_run_*.py  # Batch workflow runners
│   ├── run_*.py        # Single workflow runners
│   └── continue_*.py   # Resume paused workflows
├── runs/               # Workflow outputs (gitignored)
│   ├── workflow_*.json # State files
│   ├── dashboards/     # Per-workflow HTML
│   └── leaderboard/    # Aggregated leaderboard
├── .claude/            # Claude Code integration
│   └── skills/         # LLM skill definitions
├── settings.py         # All configuration
├── terminals.json      # MT5 terminal registry
├── mql5.pdf           # MQL5 reference documentation
├── CLAUDE.md          # Claude Code instructions
├── ROADMAP.md         # Project roadmap
└── HANDOFF.md         # Session handoff notes
```

## Directory Purposes

**engine/**
- Purpose: Core workflow orchestration
- Contains: WorkflowRunner, StateManager, gate checks, terminal registry
- Key files: `runner.py` (104KB - main orchestrator), `state.py`, `gates.py`

**modules/**
- Purpose: Individual workflow step implementations
- Contains: One module per major function (backtest, optimize, inject, etc.)
- Key files: `optimizer.py`, `backtest.py`, `monte_carlo.py`, `injector.py`

**reports/**
- Purpose: HTML report generation
- Contains: Dashboard, leaderboard, boards generators
- Key files: `workflow_dashboard.py`, `leaderboard.py`, `boards.py`

**reference/**
- Purpose: MQL5 documentation access for LLM skills
- Contains: PDF indexer and lookup utilities
- Key files: `lookup.py`, `mql5_indexer.py`

**tests/**
- Purpose: Unit and integration tests
- Contains: Pytest test files with fixtures
- Key files: `conftest.py` (shared fixtures), `test_*.py`

**scripts/**
- Purpose: User entry points
- Contains: Batch runners, single runners, cleanup utilities
- Key files: Various `run_*.py` and `continue_*.py` scripts

**runs/**
- Purpose: Workflow outputs (gitignored)
- Contains: State JSONs, HTML dashboards, leaderboard
- Subdirectories: `dashboards/`, `leaderboard/`, `boards/`

**.claude/**
- Purpose: Claude Code skill definitions
- Contains: `/stress-test`, `/param-analyzer`, `/stats-analyzer`, etc.

## Key File Locations

**Entry Points:**
- `engine/runner.py` - WorkflowRunner class
- `scripts/run_*.py` - Script entry points

**Configuration:**
- `settings.py` - All thresholds, paths, weights
- `terminals.json` - MT5 terminal registry

**Core Logic:**
- `engine/runner.py` - Workflow orchestration
- `engine/state.py` - State persistence
- `modules/optimizer.py` - MT5 optimization
- `modules/backtest.py` - MT5 backtesting
- `modules/monte_carlo.py` - Risk simulation

**Testing:**
- `tests/conftest.py` - Shared fixtures
- `tests/test_*.py` - Test files

**Documentation:**
- `CLAUDE.md` - Claude Code instructions
- `ROADMAP.md` - Project roadmap
- `HANDOFF.md` - Session handoff notes

## Naming Conventions

**Files:**
- snake_case.py: All Python modules
- UPPERCASE.md: Important project files (CLAUDE, ROADMAP, HANDOFF)
- test_*.py: Test files

**Directories:**
- lowercase: All directories
- Singular for specific purpose (engine, reference)
- Plural for collections (modules, reports, tests, scripts, runs)

**Special Patterns:**
- `__init__.py`: Package initialization
- `conftest.py`: Pytest configuration

## Where to Add New Code

**New Workflow Step:**
- Implementation: `modules/{step_name}.py`
- Integration: Add to `engine/runner.py`
- Gate: Add to `engine/gates.py`
- Tests: `tests/test_{step_name}.py`

**New Report Type:**
- Implementation: `reports/{report_name}.py`
- Template: `reports/templates/{template}.html`

**New LLM Skill:**
- Skill: `.claude/skills/{skill_name}/SKILL.md`
- Commands: `.claude/commands/{skill_name}.md`

**New Script:**
- Entry point: `scripts/{script_name}.py`

**Utilities:**
- Module utilities: Inside relevant module file
- Shared utilities: Would go in `engine/` or new `utils/`

## Special Directories

**runs/**
- Purpose: Generated workflow outputs
- Source: Created by WorkflowRunner
- Committed: No (gitignored)

**reference/cache/**
- Purpose: MQL5 PDF index cache
- Source: Generated by mql5_indexer.py
- Committed: Partially (may include pre-built index)

---

*Structure analysis: 2026-01-11*
*Update when directory structure changes*
