# Step 1B: Inject OnTester

## Overview

Creates a modified copy of the EA with an injected `OnTester()` function that returns a custom optimization criterion.

The injected criterion balances profit, equity curve smoothness (R²), trade count, and drawdown to guide genetic optimization toward robust results.

## Inputs

| Name | Type | Source | Description |
|------|------|--------|-------------|
| `ea_path` | `str` | `WorkflowRunner.ea_path` | Original EA source path |
| `inject_tester` | `bool` | Hardcoded `True` | Flag to inject OnTester |
| `inject_guards` | `bool` | Hardcoded `False` | Safety guards added in Step 1C |

## Outputs

| Name | Type | Destination | Description |
|------|------|-------------|-------------|
| `success` | `bool` | Step result | Whether injection succeeded |
| `original_path` | `str` | Step result | Path to original EA |
| `modified_path` | `str` | Step result, `runner.modified_ea_path` | Path to modified EA |
| `ontester_injected` | `bool` | Step result | Whether OnTester was injected |
| `safety_injected` | `bool` | Step result | Always `False` (done in Step 1C) |
| `errors` | `list[str]` | Step result | Error messages if any |

**Result structure:**
```python
{
    'success': True,
    'original_path': '/path/to/EA.mq5',
    'modified_path': '/path/to/EA_stress_test.mq5',
    'ontester_injected': True,
    'safety_injected': False,
    'errors': []
}
```

**Modified file naming:** `{original_stem}_stress_test.mq5`

## Gate

No explicit gate. Step passes if `success == True`.

**Pass condition:** Modified file created successfully.

**Fail condition:**
- Original file not found
- File read error
- File write error

## Implementation Notes

**Source:** `engine/runner.py:1453-1464`

```python
def _step_inject_ontester(self) -> tuple[bool, dict]:
    """Step 1B: Inject OnTester function."""
    result = create_modified_ea(
        str(self.ea_path),
        inject_tester=True,
        inject_guards=False,
    )
    if result['success']:
        self.modified_ea_path = result['modified_path']
    return result['success'], result
```

**Injection function:** `modules/injector.py:367-455`

**OnTester detection:** `modules/injector.py:256-260`

```python
def has_ontester(content: str) -> bool:
    """Check if EA already has an OnTester function."""
    pattern = r'^\s*(double|int|void)\s+OnTester\s*\(\s*\)'
    return bool(re.search(pattern, content, re.MULTILINE))
```

**Injection point selection:**
1. After last `#include` or `#property` directive
2. Or at beginning after initial comment block

**OnTester formula:** `modules/injector.py:18-135`

```
Score = Profit × R² × sqrt(trades/100) × DD_factor × PF_bonus

Where:
- Profit: TesterStatistics(STAT_PROFIT)
- R²: Linear regression of equity curve (0-1)
- trades: TesterStatistics(STAT_TRADES)
- DD_factor: 1 / (1 + maxDD/50)  [soft penalty, no hard cutoff]
- PF_bonus: 1 + (PF - 1.5) * 0.03 if PF > 1.5

Minimum trades filter: If trades < ONTESTER_MIN_TRADES, return -1000
Negative profit filter: If profit <= 0, return -500
```

**Configurable threshold:** `settings.ONTESTER_MIN_TRADES` (default: 10)

**Edge cases:**
- If EA already has `OnTester()`, injection is skipped (`ontester_injected = False`)
- EA must be valid MQL5 syntax for injection point detection
- Modified file placed in same directory as original by default

**Known issues:** None.

## Skill Integration

None. This step is fully automated.

If compilation fails after injection, the `/mql5-fixer` skill diagnoses and repairs at Step 2.
