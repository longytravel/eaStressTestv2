# Coding Conventions

**Analysis Date:** 2026-01-11

## Naming Patterns

**Files:**
- snake_case.py for all modules (e.g., `monte_carlo.py`, `stress_scenarios.py`)
- test_*.py for test files (e.g., `test_monte_carlo.py`)
- UPPERCASE.md for important docs (CLAUDE.md, ROADMAP.md, HANDOFF.md)

**Functions:**
- snake_case for all functions (e.g., `run_backtest()`, `extract_params()`)
- Prefixes: `run_` for execution, `create_` for generation, `parse_` for parsing
- Private helpers: `_` prefix (e.g., `_log()`, `_save()`, `_make_report_name()`)

**Variables:**
- snake_case for variables (e.g., `workflow_id`, `ea_path`)
- UPPER_SNAKE_CASE for module-level constants in `settings.py`
- No underscore prefix for instance attributes

**Types:**
- PascalCase for classes (e.g., `WorkflowRunner`, `StateManager`)
- No type annotations in most code (Python duck typing)
- Type hints present in function signatures: `list[dict]`, `Optional[str]`

## Code Style

**Formatting:**
- 4 space indentation
- Single quotes for strings
- No explicit formatter detected (manual formatting)
- Line length: ~100 characters typical

**Imports:**
- Standard library first, then local imports
- `sys.path.insert(0, ...)` pattern for project root access
- Direct module imports preferred over `from x import *`

## Import Organization

**Order:**
1. Standard library (`json`, `os`, `pathlib`, `datetime`)
2. Path setup (`sys.path.insert(0, ...)`)
3. Local modules (`from engine.state import StateManager`)
4. Settings (`import settings`)

**Pattern Example:**
```python
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import settings
```

## Error Handling

**Patterns:**
- Try/catch at workflow step boundaries
- Errors stored in `state.errors[]` array
- Step status set to `failed` on exception
- Best-effort cleanup (e.g., `_terminate_terminal_processes()`)

**Error Types:**
- `FileNotFoundError` for missing files/workflows
- Generic `Exception` catch with error string storage
- No custom exception classes

## Logging

**Framework:**
- Print statements to console
- `on_progress` callback for progress messages

**Patterns:**
- `_log()` helper method on WorkflowRunner
- Errors captured in state JSON

## Comments

**When to Comment:**
- Module docstrings at top of each file
- Function docstrings with Args/Returns sections
- Inline comments for non-obvious logic

**Docstring Format:**
```python
def run_backtest(...) -> dict:
    """
    Run a single backtest.

    Args:
        ea_name: EA filename (e.g., "MyEA.ex5")
        symbol: Trading symbol
        ...

    Returns:
        dict with success, profit, etc.
    """
```

**TODO Comments:**
- Not commonly used in this codebase
- Discovered work tracked in `.beads/` instead

## Function Design

**Size:**
- Varies widely (some functions 300+ lines in runner.py)
- Helpers extracted for reusable logic

**Parameters:**
- Named parameters preferred
- Optional parameters with defaults: `symbol: str = 'EURUSD'`
- Type hints: `Optional[str]`, `list[dict]`

**Return Values:**
- Dict return for complex results (common pattern)
- Boolean for simple pass/fail
- None for side-effect functions

## Module Design

**Exports:**
- Direct function imports from modules
- No `__all__` declarations
- Dynamic loading via `load_module()` in runner

**Initialization:**
- `__init__.py` files present but minimal
- Lazy loading pattern in `engine/runner.py`

## Configuration Pattern

**settings.py:**
- All constants in single module
- Grouped by section with comment headers
- Functions for dynamic values (e.g., `get_backtest_dates()`)
- No environment variable usage

---

*Convention analysis: 2026-01-11*
*Update when patterns change*
