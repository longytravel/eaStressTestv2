# Step 1C: Inject Safety

## Overview

Injects safety guards into the modified EA to enforce spread and slippage limits during testing.

This step modifies the file created in Step 1B, adding:
1. **Compile-time safety macros** - Disable dangerous operations (file I/O, web requests)
2. **Trade safety guards** - Intercept `OrderSend` to enforce spread/slippage limits

## Inputs

| Name | Type | Source | Description |
|------|------|--------|-------------|
| `modified_ea_path` | `str` | `runner.modified_ea_path` | Path from Step 1B |

## Outputs

| Name | Type | Destination | Description |
|------|------|-------------|-------------|
| `safety_injected` | `bool` | Step result | Whether guards were injected |
| `path` | `str` | Step result | Path to modified EA |

**Result structure:**
```python
{
    'safety_injected': True,
    'path': '/path/to/EA_stress_test.mq5'
}
```

## Gate

No explicit gate. Step passes if `modified_ea_path` exists from Step 1B.

**Pass condition:** Safety guards injected (or already present).

**Fail condition:** No modified EA from Step 1B.

## Implementation Notes

**Source:** `engine/runner.py:1466-1477`

```python
def _step_inject_safety(self) -> tuple[bool, dict]:
    """Step 1C: Inject safety guards."""
    if not self.modified_ea_path:
        return False, {'error': 'No modified EA from previous step'}

    from modules.injector import inject_safety
    content = Path(self.modified_ea_path).read_text(encoding='utf-8')
    content, injected = inject_safety(content)
    Path(self.modified_ea_path).write_text(content, encoding='utf-8')

    return True, {'safety_injected': injected, 'path': self.modified_ea_path}
```

**Safety injection:** `modules/injector.py:313-364`

### Injected Code

**1. Compile-time safety macros:** `modules/injector.py:145-164`

```cpp
#define STRESS_TEST_MODE true

#ifdef STRESS_TEST_MODE
    // Prevent file operations
    #define FileOpen(a,b,c) INVALID_HANDLE
    #define FileWrite(a,b) 0
    #define FileDelete(a) false

    // Prevent web requests
    #define WebRequest(a,b,c,d,e,f,g) false

    // Prevent DLL calls
    #define DLLCall(a,b) 0
#endif
```

**2. Trade safety inputs:** `modules/injector.py:166-253`

```cpp
input double EAStressSafety_MaxSpreadPips = 3.0;     // Max allowed spread (pips)
input double EAStressSafety_MaxSlippagePips = 3.0;   // Max allowed slippage (pips)
```

These inputs are:
- **Visible** in extracted params (Step 3)
- **Never optimized** (marked non-optimizable by param extractor)
- **Overridden at runtime:**
  - Step 5 validation: Set to 500 pips (effectively disabled)
  - Optimization/backtests: Set to configured defaults

**3. OrderSend interceptor:** `modules/injector.py:205-252`

```cpp
bool EAStressSafety_OrderSend(const MqlTradeRequest& request, MqlTradeResult& result)
{
    if(!EAStressSafety_IsSpreadOk())
    {
        result.retcode = 0;
        result.comment = "EAStressSafety: Spread too high";
        return false;
    }
    // ... cap deviation if EA set looser value ...
    return OrderSend(req, result);
}

#define OrderSend EAStressSafety_OrderSend
#define OrderSendAsync EAStressSafety_OrderSendAsync
```

### Configurable Thresholds

From `settings.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `SAFETY_DEFAULT_MAX_SPREAD_PIPS` | 3.0 | Spread limit for optimization/backtests |
| `SAFETY_DEFAULT_MAX_SLIPPAGE_PIPS` | 3.0 | Slippage limit for optimization/backtests |
| `SAFETY_VALIDATION_MAX_SPREAD_PIPS` | 500.0 | Loosened for Step 5 trade validation |
| `SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS` | 500.0 | Loosened for Step 5 trade validation |

**Edge cases:**
- If safety guards already present (`STRESS_TEST_MODE` defined), injection is skipped
- Trade safety can be injected separately (upgrades older injected files)
- Injection point: After initial comment block, or after existing safety block

**Known issues:** None.

## Skill Integration

None. This step is fully automated.

Safety params appear in extracted params but are excluded from optimization. The runner forces their values based on context (validation vs optimization).
