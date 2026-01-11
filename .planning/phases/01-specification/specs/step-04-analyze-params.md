# Step 4: Analyze Parameters

**Status:** Workflow pause point
**Skill Integration:** `/param-analyzer` (required)
**Gate:** Parameters analyzed and both outputs provided

---

## Overview

Step 4 is the first LLM integration point in the workflow. After Step 3 extracts raw parameters from the EA source, the workflow **pauses** and waits for intelligent parameter analysis.

The `/param-analyzer` skill analyzes extracted parameters and produces TWO required outputs:
1. **wide_validation_params** — Single values to maximize trading for validation
2. **initial_optimization_ranges** — Wide ranges for comprehensive exploration

This is EXPLORATION, not optimization. Include all potentially relevant parameters.

---

## Inputs

### From Step 3 (Extract Params)
```python
params: list[dict]
# Each param has:
{
    "name": str,           # Parameter name (e.g., "RSI_Period")
    "type": str,           # MQL5 type (e.g., "input int")
    "base_type": str,      # Normalized type (int, double, bool, string, enum)
    "default": Any,        # Default value from source
    "comment": str,        # Inline comment (may describe purpose)
    "optimizable": bool,   # True if numeric and not magic number
}
```

### From Workflow State
```python
ea_path: str           # Path to original EA source
symbol: str            # Trading symbol (e.g., "GBPUSD")
timeframe: str         # Timeframe (e.g., "H1")
```

---

## Outputs

### Output 1: wide_validation_params
```python
wide_validation_params: dict[str, Any]
# Dict of param_name -> single value
# Example:
{
    "RSI_Period": 14,
    "Use_RSI_Filter": False,  # Disable filter to maximize trades
    "Max_Spread": 500,        # Very permissive
    "Trading_Start_Hour": 0,  # Trade all hours
    "Trading_End_Hour": 23,
}
```

**Purpose:** Maximize trade count for Step 5 validation (target: 50+ trades)

**Requirements:**
- Remove all filters (set to permissive values or disable)
- Extend time windows to maximum
- Set all thresholds to permissive values
- Enable features that generate more signals

### Output 2: initial_optimization_ranges
```python
initial_optimization_ranges: list[dict]
# Each entry describes one parameter's optimization behavior
{
    "name": str,             # Parameter name
    "start": number | bool,  # Start value (or first boolean)
    "step": number,          # Step size (or None for bool)
    "stop": number | bool,   # Stop value (or second boolean)
    "optimize": bool,        # True = include in optimization
    "fixed_value": Any,      # If optimize=False, use this value
    "skip_reason": str,      # If skipped, why (optional)
}
```

**Purpose:** Comprehensive exploration of parameter space

**Critical Requirement — Include ALL Parameters:**
The initial optimization must include ALL potentially relevant parameters. The genetic optimizer handles large search spaces. Refinement happens AFTER Step 8 via the `/optimization-loop` skill.

---

## Parameters to EXCLUDE

Only exclude parameters that genuinely cannot affect strategy performance:

| Category | Examples | Reason |
|----------|----------|--------|
| **Identifiers** | Magic_Number, EA_ID, UniqueID | Labels only, no trading impact |
| **Pure Cosmetics** | Arrow_Color, Line_Width, Font_Size | Visual only, zero trade impact |
| **Debug/Development** | Verbose_Logging, Debug_Mode, Print_Trades | Development aids |
| **String Metadata** | Comment_Prefix, Order_Comment | Labels only |

**DO NOT exclude based on name patterns alone.** Read the EA code to understand what each parameter actually does.

---

## Parameters to INCLUDE

Include all parameters that could affect trading performance:

| Category | Examples | Why Include |
|----------|----------|-------------|
| **Strategy Core** | RSI_Period, MA_Period, Entry_Level | Directly affects signals |
| **Feature Toggles** | Use_RSI_Filter, Enable_Session_Filter | On/off may be optimal either way |
| **Time Filters** | Trading_Start_Hour, Friday_Close_Hour | Session timing affects performance |
| **Risk/Money** | Stop_Loss, Take_Profit, Lot_Size | Risk profile affects results |
| **Secondary Filters** | Max_Spread, Max_Slippage, Min_Volatility | Filter stringency matters |

---

## Range Guidelines

Target **8-15 values per continuous parameter**:

```python
# Example: RSI Period (core parameter - finer steps)
{"name": "RSI_Period", "start": 7, "step": 2, "stop": 21, "optimize": True}
# Values: 7, 9, 11, 13, 15, 17, 19, 21 (8 values)

# Example: Max Spread (secondary filter - coarser steps)
{"name": "Max_Spread", "start": 10, "step": 10, "stop": 50, "optimize": True}
# Values: 10, 20, 30, 40, 50 (5 values)

# Example: Boolean toggle (test both)
{"name": "Use_Filter", "start": False, "step": 1, "stop": True, "optimize": True}
# Values: False, True (2 values)
```

**Do NOT artificially limit combinations.** The genetic optimizer handles large spaces efficiently. Refinement happens after Step 8.

---

## Toggle-Dependent Parameters

**Critical Rule:** When optimizing a toggle (`Enable_X`, `Use_X`), also optimize its dependent parameters.

```python
# BAD - dependent params have arbitrary fixed values
{"name": "Enable_Session_Filter", "optimize": True},
{"name": "Session_Start_Hour", "optimize": False, "fixed_value": 8},  # WRONG

# GOOD - dependent params also optimized
{"name": "Enable_Session_Filter", "optimize": True},
{"name": "Session_Start_Hour", "start": 7, "step": 1, "stop": 11, "optimize": True},
{"name": "Session_End_Hour", "start": 16, "step": 1, "stop": 20, "optimize": True},
```

---

## Workflow Pause State

After Step 3 completes, the workflow enters pause state:

```python
state = {
    "status": "awaiting_param_analysis",
    "steps": {
        "1_load_ea": {"passed": True, ...},
        "1b_inject_ontester": {"passed": True, ...},
        "1c_inject_safety": {"passed": True, ...},
        "2_compile": {"passed": True, ...},
        "3_extract_params": {"passed": True, "result": {"params": [...]}},
    }
}
```

---

## Resume Mechanism

Resume via `runner.continue_with_params()`:

```python
# Code reference: engine/runner.py:712-802

def continue_with_params(
    self,
    wide_validation_params: dict,
    optimization_ranges: list[dict],
    stop_on_failure: bool = True,
    force: bool = False,
) -> dict:
    """
    Continue workflow from Step 4 with Claude-analyzed parameters.

    Args:
        wide_validation_params: Dict of {param_name: value} for validation
        optimization_ranges: List of param dicts with start/step/stop
        stop_on_failure: If True, stop at first failed gate
        force: If True, allow re-running even if Step 4 already completed
    """
```

**Prerequisite Validation:**
- Steps 1, 1B, 1C, 2, 3 must have passed
- Raises `ValueError` if prerequisites not met

**Param Validation:**
- Checks that submitted params are well-formed
- Raises `ValueError` if validation fails

**Safety Handling:**
- Automatically applies injected safety param defaults
- Forces safety params to loose values for validation
- Forces safety params to fixed values for optimization

---

## Gate

**Name:** `4_analyze_params`
**Condition:** Both outputs provided and valid

**Validation checks:**
1. `wide_validation_params` is a non-empty dict
2. `optimization_ranges` is a non-empty list
3. Each range has required fields: name, start, step, stop, optimize
4. Range values are sensible (start ≤ stop for non-bool, step > 0)

**Gate result stored:**
```python
state.steps["4_analyze_params"] = {
    "passed": True,
    "result": {
        "source": "claude_analysis",
        "wide_validation_params": {...},
        "wide_param_count": N,
        "optimization_ranges": [...],
        "optimization_param_count": M,
    }
}
```

---

## Skill Integration: /param-analyzer

### Trigger
- Workflow status is `awaiting_param_analysis`
- User invokes `/param-analyzer`
- Automatically invoked by `/stress-test` skill

### Input to Skill
```python
{
    "params": [...],           # From Step 3
    "ea_path": str,           # For reading EA source
    "symbol": str,
    "timeframe": str,
}
```

### Output from Skill
```python
{
    "wide_validation_params": {...},
    "optimization_ranges": [...],
}
```

### Skill Responsibilities
1. Read and understand the full EA source
2. Map each parameter to its role in trading logic
3. Generate wide_validation_params (maximize trades)
4. Generate optimization_ranges (comprehensive exploration)
5. Apply toggle-dependency rules
6. Apply timezone-aware hour ranges

See: `.claude/skills/param-analyzer/SKILL.md`

---

## Handoff to Optimization Loop

After Step 4 completes:
1. **Step 5:** Validation backtest with wide_validation_params
2. **Step 6:** Create INI with optimization_ranges
3. **Step 7:** Run genetic optimization
4. **Step 8:** Parse results
5. **Step 8B:** Select top passes (LLM or auto)

If optimization results are poor, the `/optimization-loop` skill can refine ranges based on evidence. The initial ranges from this step are for EXPLORATION — refinement comes later.

---

## Implementation Notes

### Code References
- `engine/runner.py:712-802` — `continue_with_params()` method
- `engine/runner.py:769-776` — Param validation logic
- `engine/runner.py:779-781` — Safety param handling

### Settings References
- `settings.SAFETY_VALIDATION_MAX_SPREAD_PIPS` — Loose spread for validation
- `settings.SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS` — Loose slippage for validation

### Error Handling
- `ValueError` if prerequisites not met
- `ValueError` if param submission invalid
- `RuntimeError` if Step 4 already completed (unless force=True)

---

*Spec version: 1.0*
*Last updated: 2026-01-11*
