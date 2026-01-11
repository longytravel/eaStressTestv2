---
phase: 03-mt5-abstraction
plan: 01
subsystem: mt5
tags: [protocol, abstraction, testing, python]

# Dependency graph
requires:
  - phase: 02-core-domain
    provides: [domain models, dataclass patterns, serialization approach]
provides:
  - MT5Interface protocol (compile, backtest, optimize)
  - CompileResult, BacktestResult, OptimizationResult dataclasses
  - TerminalMT5 implementation (wraps existing modules)
  - DryRunMT5 implementation (mock for testing)
affects: [04-workflow-engine, testing infrastructure]

# Tech tracking
tech-stack:
  added: []
  patterns: [typing.Protocol for structural subtyping, frozen dataclasses for results, lazy imports via __getattr__]

key-files:
  created:
    - ea_stress/mt5/__init__.py
    - ea_stress/mt5/interface.py
    - ea_stress/mt5/terminal.py
    - ea_stress/mt5/dry_run.py
  modified: []

key-decisions:
  - "Use Protocol instead of ABC for structural subtyping"
  - "Use frozen=True for result dataclasses (immutable operation results)"
  - "Use tuples instead of lists in frozen dataclasses (hashable)"
  - "Lazy import implementations via __getattr__ to avoid circular imports"
  - "TerminalMT5 imports existing modules inside methods (not at module level)"

patterns-established:
  - "MT5 operations return typed result dataclasses instead of dicts"
  - "Implementations satisfy Protocol through duck typing (no inheritance)"
  - "DryRunMT5.call_log tracks all operations for test assertions"

issues-created: []

# Metrics
duration: 10min
completed: 2026-01-11
---

# Phase 03-mt5-abstraction Plan 01: MT5 Abstraction Layer Summary

**Interface protocol and implementations for MT5 operations enabling testable workflow stages**

## Performance

- **Duration:** 10 min
- **Started:** 2026-01-11T21:00:00Z
- **Completed:** 2026-01-11T21:10:00Z
- **Tasks:** 3
- **Files created:** 4

## Accomplishments

- Created ea_stress/mt5/ package with interface protocol
- Defined CompileResult, BacktestResult, OptimizationResult frozen dataclasses
- Implemented TerminalMT5 wrapping modules/compiler.py, modules/backtest.py, modules/optimizer.py
- Implemented DryRunMT5 with configurable responses and call logging
- All result types have to_dict/from_dict for serialization
- Existing modules unchanged - TerminalMT5 is a thin adapter

## Task Commits

Each task completed atomically:

1. **Task 1: Create MT5 interface protocol** - interface.py with Protocol and result dataclasses
2. **Task 2: Create terminal implementation** - terminal.py wrapping existing modules
3. **Task 3: Create dry-run implementation** - dry_run.py for testing without MT5

## Files Created

- `ea_stress/mt5/__init__.py` - Package with exports and lazy imports
- `ea_stress/mt5/interface.py` - MT5Interface Protocol, CompileResult, BacktestResult, OptimizationResult
- `ea_stress/mt5/terminal.py` - TerminalMT5 wrapping modules/compiler, backtest, optimizer
- `ea_stress/mt5/dry_run.py` - DryRunMT5 with configurable mock responses

## Decisions Made

1. **Protocol vs ABC** - Used Protocol for structural subtyping; implementations don't need to inherit
2. **Frozen dataclasses** - All result types are immutable snapshots of operation outcomes
3. **Tuples for sequences** - Used tuple instead of list in frozen dataclasses for hashability
4. **Lazy imports** - __getattr__ in __init__.py avoids circular imports when importing implementations
5. **Method-level imports in TerminalMT5** - Avoids importing modules at package import time

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all modules implemented and verified successfully.

## Verification Results

All verification checks passed:
- `from ea_stress.mt5 import MT5Interface, TerminalMT5, DryRunMT5` - OK
- `from ea_stress.mt5 import CompileResult, BacktestResult, OptimizationResult` - OK
- DryRunMT5 instantiates and operates without MT5 - OK
- TerminalMT5 instantiates (imports succeed) - OK
- Result dataclasses have to_dict/from_dict - OK
- No modifications to modules/ files - OK
- pytest: 243 tests passed - OK

## API Overview

### Result Dataclasses

```python
@dataclass(frozen=True)
class CompileResult:
    success: bool
    exe_path: str | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class BacktestResult:
    success: bool
    profit: float
    profit_factor: float
    max_drawdown_pct: float
    total_trades: int
    win_rate: float
    sharpe_ratio: float
    expected_payoff: float
    recovery_factor: float
    equity_curve: tuple[float, ...]
    report_path: str | None
    errors: tuple[str, ...]

@dataclass(frozen=True)
class OptimizationResult:
    success: bool
    passes_count: int
    results: tuple[dict, ...]
    best_result: dict | None
    xml_path: str | None
    errors: tuple[str, ...]
```

### MT5Interface Protocol

```python
class MT5Interface(Protocol):
    def compile(self, ea_path: Path) -> CompileResult: ...
    def backtest(self, ea_path: Path, symbol: str, timeframe: str, ...) -> BacktestResult: ...
    def optimize(self, ea_path: Path, symbol: str, timeframe: str, param_ranges: list[dict], ...) -> OptimizationResult: ...
```

### Usage

```python
# Production
from ea_stress.mt5 import TerminalMT5
mt5 = TerminalMT5()
result = mt5.compile(Path("MyEA.mq5"))

# Testing
from ea_stress.mt5 import DryRunMT5
mt5 = DryRunMT5(compile_success=True, backtest_trades=50)
result = mt5.compile(Path("MyEA.mq5"))
assert result.success
assert mt5.call_log[0] == ("compile", {"ea_path": Path("MyEA.mq5")})
```

## Next Phase Readiness

Phase 03-01 complete. MT5 abstraction ready for use by:
- Phase 4: Workflow Engine (will use MT5Interface for operations)
- Testing infrastructure (DryRunMT5 enables unit tests without MT5)

---
*Phase: 03-mt5-abstraction*
*Completed: 2026-01-11*
