# Step 5: Validate Trades

**Status:** Automatic step
**Gate:** MIN_TRADES threshold (default: 50)
**On Failure:** Transitions to Step 5B (Fix EA)

---

## Overview

Step 5 runs a validation backtest using the **wide_validation_params** from Step 4. The purpose is to PROVE the EA can generate enough trades for statistically meaningful optimization.

The validation backtest uses:
- Wide (permissive) parameter settings
- Standard 4-year backtest period (3 in-sample + 1 forward)
- 1-minute OHLC data model with 10ms latency
- Loosened safety parameters

If the EA produces fewer than MIN_TRADES, the workflow transitions to Step 5B (Fix EA).

---

## Inputs

### From Step 4 (Analyze Params)
```python
wide_validation_params: dict[str, Any]
# Dict of param_name -> single value
# Example:
{
    "RSI_Period": 14,
    "Use_RSI_Filter": False,      # Disabled to maximize trades
    "Max_Spread": 500,            # Very permissive
    "Trading_Start_Hour": 0,      # Trade all hours
    "Trading_End_Hour": 23,
}
```

### From Previous Steps
```python
compiled_ea_path: str   # Path to compiled .ex5 file (from Step 2)
symbol: str             # Trading symbol (from workflow init)
timeframe: str          # Timeframe (from workflow init)
terminal: dict          # Terminal configuration
```

---

## Process

### 1. Create Validation Backtest
```python
# Code reference: engine/runner.py:1516-1540

report_name = self._make_report_name('S5_validate', f'{self.symbol}_{self.timeframe}')

result = run_backtest(
    self.compiled_ea_path,
    symbol=self.symbol,
    timeframe=self.timeframe,
    terminal=self.terminal,
    params=self.wide_validation_params,  # Wide params from Step 4
    report_name=report_name,
)
```

### 2. Check Trade Count Gate
```python
# Code reference: engine/gates.py:93-103

trades = result.get('total_trades', 0)
gate = gates.check_minimum_trades(trades)
# Returns GateResult with:
#   passed: trades >= settings.MIN_TRADES
#   value: trades
#   threshold: settings.MIN_TRADES
```

---

## Backtest Settings

### Period Settings
```python
# Code reference: settings.py:11-24

BACKTEST_YEARS = 4        # Total period
IN_SAMPLE_YEARS = 3       # In-sample portion
FORWARD_YEARS = 1         # Forward test portion

def get_backtest_dates():
    """Calculate dynamic backtest dates ending today."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=BACKTEST_YEARS * 365)
    split_date = end_date - timedelta(days=FORWARD_YEARS * 365)
    return {
        "start": start_date.strftime("%Y.%m.%d"),
        "end": end_date.strftime("%Y.%m.%d"),
        "split": split_date.strftime("%Y.%m.%d"),
    }
```

### Data Model Settings
```python
# Code reference: settings.py:35-42

DATA_MODEL = 1              # 1-minute OHLC
EXECUTION_LATENCY_MS = 10   # 10ms execution latency
```

### Account Settings
```python
# Code reference: settings.py:55-58

DEPOSIT = 3000
CURRENCY = "GBP"
LEVERAGE = 100
```

---

## Safety Parameter Handling

**Critical:** During validation, injected safety parameters are LOOSENED to avoid false "no trades" failures.

```python
# Code reference: settings.py:47-53

# EA-level safety defaults (injected into EAs that don't have these)
SAFETY_DEFAULT_MAX_SPREAD_PIPS = 3.0
SAFETY_DEFAULT_MAX_SLIPPAGE_PIPS = 3.0

# During Step 5 (trade validation), we loosen safety limits
SAFETY_VALIDATION_MAX_SPREAD_PIPS = 500.0
SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS = 500.0
```

The runner automatically applies these loose values via `_apply_injected_safety_defaults()`:
- `MaxSpreadPips` → 500.0 for validation
- `MaxSlippagePips` → 500.0 for validation

This prevents tight safety filters from blocking trades during the "can this EA trade?" validation.

---

## Gate

**Name:** `minimum_trades`
**Threshold:** `settings.MIN_TRADES` (default: 50)
**Operator:** `>=`

### Gate Logic
```python
# Code reference: engine/gates.py:93-103

def check_minimum_trades(total_trades: int) -> GateResult:
    """Gate 5: Check minimum trade count."""
    passed = total_trades >= settings.MIN_TRADES
    return GateResult(
        name='minimum_trades',
        passed=passed,
        value=total_trades,
        threshold=settings.MIN_TRADES,
        operator='>=',
        message=f"{'PASS' if passed else 'FAIL'}: {total_trades} trades (minimum: {settings.MIN_TRADES})"
    )
```

### Settings Reference
```python
# Code reference: settings.py:75

MIN_TRADES = 50  # Minimum trades for statistical significance
```

---

## Outputs

### On Success (≥50 trades)
```python
state.steps["5_validate_trades"] = {
    "passed": True,
    "result": {
        "success": True,
        "total_trades": N,          # ≥ 50
        "profit": float,
        "profit_factor": float,
        "max_drawdown_pct": float,
        "report_path": str,
        "gate": {
            "name": "minimum_trades",
            "passed": True,
            "value": N,
            "threshold": 50,
            "operator": ">=",
        }
    }
}
```

### On Failure (<50 trades)
```python
state.steps["5_validate_trades"] = {
    "passed": False,
    "result": {
        "success": True,            # Backtest ran successfully
        "total_trades": N,          # < 50
        "gate": {
            "name": "minimum_trades",
            "passed": False,
            "value": N,
            "threshold": 50,
        }
    }
}
```

---

## Data Flow

```
Step 4 Output               Step 5 Process              Step 5 Output
┌─────────────────┐        ┌──────────────────┐        ┌──────────────────┐
│ wide_validation │───────▶│ run_backtest()   │───────▶│ total_trades: N  │
│    _params      │        │ with wide params │        │ gate: pass/fail  │
└─────────────────┘        └──────────────────┘        └──────────────────┘
                                   │
                                   ▼
                           ┌──────────────────┐
                           │ check_minimum_   │
                           │ trades(N)        │
                           └──────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
              PASS (N ≥ 50)                FAIL (N < 50)
                    │                             │
                    ▼                             ▼
              Step 6 (INI)                  Step 5B (Fix)
```

---

## Failure Handling

When validation fails (< MIN_TRADES):

```python
# Code reference: engine/runner.py:830-847

if not passed:
    self._log("Step 5_validate_trades FAILED")

    # Check if we can attempt a fix
    if self.fix_attempts < self.max_fix_attempts:
        self.fix_attempts += 1
        self.state.set('fix_attempts', self.fix_attempts)
        self.state.set('max_fix_attempts', self.max_fix_attempts)
        self.state.set_status('awaiting_ea_fix')

        self._log(f"PAUSED: Awaiting EA fix (attempt {self.fix_attempts}/{self.max_fix_attempts})")
        self._log("Invoke /mql5-fixer skill to diagnose and fix the EA")

        return self.state.get_summary()
    else:
        self._log(f"Max fix attempts ({self.max_fix_attempts}) reached - workflow failed")
        self.state.complete_workflow(False)
        return self.state.get_summary()
```

---

## Implementation Notes

### Code References
- `engine/runner.py:1516-1540` — `_step_validate_trades()` method
- `engine/runner.py:814-852` — `_run_phase2()` with failure handling
- `modules/backtest.py:164-457` — `run_backtest()` function
- `engine/gates.py:93-103` — `check_minimum_trades()` gate

### Backtest Execution
The validation backtest uses `modules/backtest.py:run_backtest()` which:
1. Creates INI file with params
2. Launches MT5 terminal
3. Waits for completion (timeout: 600s)
4. Parses HTML report for results

### Report Naming
```python
report_name = self._make_report_name('S5_validate', f'{symbol}_{timeframe}')
# Example: S5_validate_GBPUSD_H1_20260111_143052
```

Deterministic naming prevents report collisions.

---

*Spec version: 1.0*
*Last updated: 2026-01-11*
