# MQL5 Fixer Skill

Fixes MQL5 code issues - both compilation errors AND trade validation failures.

## Triggers

1. **Step 2 Failure**: Compilation errors - fix syntax/type/function errors
2. **Step 5B Failure**: Trade validation fails - diagnose why EA isn't trading enough

User says: `/mql5-fixer` or workflow status is `awaiting_ea_fix`

## Purpose

### For Compilation Errors (Step 2)
1. Parse compilation error messages
2. Identify the root cause
3. Look up correct syntax via `/mql5-lookup`
4. Generate specific fix with code

### For Trade Validation Failures (Step 5B)
1. Diagnose WHY the EA isn't generating enough trades
2. Identify hardcoded values, bugs, or overly strict conditions
3. **ASK PERMISSION** before making any modifications
4. Backup original EA before changes
5. Propose specific fixes to enable more trades
6. Max 3 attempts - then report failure to user

---

## Input

Compilation output from `modules/compiler.py`:
```json
{
  "success": false,
  "errors": [
    {
      "file": "MyEA.mq5",
      "line": 45,
      "column": 12,
      "code": "C4756",
      "message": "implicit conversion from 'number' to 'string'"
    }
  ],
  "warnings": [...]
}
```

---

## Error Categories

### Category 1: Syntax Errors

| Error Pattern | Cause | Fix Template |
|--------------|-------|--------------|
| `'X' - undeclared identifier` | Variable not declared | Add declaration |
| `'X' - function not defined` | Missing function | Add function or include |
| `';' expected` | Missing semicolon | Add semicolon |
| `'{' expected` / `'}' expected` | Bracket mismatch | Fix brackets |
| `')' expected` | Parenthesis mismatch | Fix parentheses |

### Category 2: Type Errors

| Error Pattern | Cause | Fix Template |
|--------------|-------|--------------|
| `implicit conversion` | Type mismatch | Cast or change type |
| `cannot convert` | Incompatible types | Use correct type |
| `wrong type` | Parameter type error | Check function signature |
| `array required` | Expected array | Use array syntax |

### Category 3: Function Errors

| Error Pattern | Cause | Fix Template |
|--------------|-------|--------------|
| `wrong parameters count` | Missing/extra args | Check signature |
| `function is not defined` | Missing include | Add include |
| `'OnInit' - function must return` | Missing return | Add return statement |
| `cannot call` | Wrong usage | Check documentation |

### Category 4: Trade Errors

| Error Pattern | Cause | Fix Template |
|--------------|-------|--------------|
| `OrderSend` errors | Wrong request format | Fix MqlTradeRequest |
| `Position` errors | Wrong position handling | Use PositionSelect first |
| `Invalid stops` | SL/TP calculation wrong | Fix price calculations |

---

## Fix Process

### Step 1: Parse Error
```python
def parse_error(error):
    return {
        "file": error['file'],
        "line": error['line'],
        "code": error['code'],
        "message": error['message'],
        "category": categorize_error(error['message']),
        "identifier": extract_identifier(error['message']),
    }
```

### Step 2: Read Context
```python
def get_context(file, line, context_lines=5):
    lines = read_file(file)
    start = max(0, line - context_lines)
    end = min(len(lines), line + context_lines)

    return {
        "before": lines[start:line-1],
        "error_line": lines[line-1],
        "after": lines[line:end],
    }
```

### Step 3: Identify Fix
```python
def identify_fix(error, context):
    if error['category'] == 'undeclared':
        # Look for similar variable names (typo?)
        similar = find_similar_in_file(error['identifier'])
        if similar:
            return {"type": "typo", "suggestion": similar}

        # Check if it's a function that needs include
        if looks_like_function(error['identifier']):
            include = lookup_required_include(error['identifier'])
            return {"type": "missing_include", "include": include}

        # Needs declaration
        return {"type": "missing_declaration", "identifier": error['identifier']}
```

### Step 4: Generate Fix
```python
def generate_fix(error, fix_info, context):
    if fix_info['type'] == 'typo':
        return {
            "action": "replace",
            "old": error['identifier'],
            "new": fix_info['suggestion'],
            "explanation": f"Typo: '{error['identifier']}' should be '{fix_info['suggestion']}'"
        }

    if fix_info['type'] == 'missing_include':
        return {
            "action": "add_include",
            "include": fix_info['include'],
            "location": "top of file",
            "explanation": f"Add include for {error['identifier']}"
        }
```

### Step 5: Validate with Lookup
```python
def validate_fix(fix, error):
    # Use mql5-lookup to verify syntax
    if fix['action'] == 'replace_function':
        correct_signature = mql5_lookup(fix['function'])
        return correct_signature
```

---

## Common Fixes

### Missing Include
```
Error: 'CTrade' - undeclared identifier

Fix:
Add at top of file:
#include <Trade\Trade.mqh>
```

### Wrong Function Signature
```
Error: 'PositionGetDouble' - wrong parameters count

Lookup: PositionGetDouble requires:
  ENUM_POSITION_PROPERTY_DOUBLE property_id

Fix:
Replace: PositionGetDouble(POSITION_PROFIT, profit)
With:    profit = PositionGetDouble(POSITION_PROFIT)
```

### Type Conversion
```
Error: implicit conversion from 'number' to 'string'

Context line 45:
  Print("Price: " + price);

Fix:
Replace: Print("Price: " + price)
With:    Print("Price: ", DoubleToString(price, _Digits))

Or simpler:
With:    Print("Price: ", price)  // Print handles mixed types
```

### Missing Return
```
Error: 'OnInit' - function must return a value

Fix:
Add at end of OnInit:
return(INIT_SUCCEEDED);
```

### Invalid Stops
```
Error: Invalid stops (common runtime, but can be compile-time constant)

Context:
  trade.Buy(lots, _Symbol, ask, ask - 50, ask + 100);

Fix:
Replace: ask - 50
With:    NormalizeDouble(ask - 50 * _Point, _Digits)

Full fix:
double sl = NormalizeDouble(ask - StopLoss * _Point, _Digits);
double tp = NormalizeDouble(ask + TakeProfit * _Point, _Digits);
trade.Buy(lots, _Symbol, ask, sl, tp);
```

---

## Output Format

### Single Error Fix
```markdown
## Fix for Line 45: undeclared identifier 'CTrade'

### Problem
The `CTrade` class is used but not imported.

### Solution
Add this include at the top of your file:

```mql5
#include <Trade\Trade.mqh>
```

### After Fix
```mql5
#property copyright "..."
#property version "1.00"

#include <Trade\Trade.mqh>  // ADD THIS LINE

input double LotSize = 0.1;
// ... rest of code
```
```

### Multiple Error Report
```markdown
## Compilation Fixes: MyEA.mq5

### Summary
- 3 errors found
- 2 warnings (can ignore)

---

### Error 1: Line 45 - Missing include

**Message**: `'CTrade' - undeclared identifier`

**Fix**: Add `#include <Trade\Trade.mqh>` at file top

---

### Error 2: Line 78 - Wrong parameter count

**Message**: `'iRSI' - wrong parameters count`

**Current code**:
```mql5
rsi_handle = iRSI(14, PRICE_CLOSE);
```

**Fixed code**:
```mql5
rsi_handle = iRSI(_Symbol, PERIOD_CURRENT, 14, PRICE_CLOSE);
```

**Explanation**: iRSI requires 4 parameters: symbol, timeframe, period, price type

---

### Error 3: Line 102 - Type mismatch

**Message**: `cannot convert string to double`

**Current code**:
```mql5
double price = SymbolInfoString(_Symbol, SYMBOL_BID);
```

**Fixed code**:
```mql5
double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
```

**Explanation**: BID price is a double, use SymbolInfoDouble not SymbolInfoString

---

## All Fixes Summary

1. Add include at top: `#include <Trade\Trade.mqh>`
2. Line 78: Add _Symbol and PERIOD_CURRENT to iRSI call
3. Line 102: Change SymbolInfoString to SymbolInfoDouble

After applying these fixes, recompile the EA.
```

---

## Integration

- **Workflow Step 2**: Called automatically when compilation fails
- **ea-improver**: Uses for fixing suggested code
- **mql5-lookup**: Used to verify correct syntax

## Dependencies

- `modules/compiler.py` - Compilation output
- `/mql5-lookup` - Reference documentation
- EA source file access

---

## Validation Anti-Patterns

Detect and warn about:

| Anti-Pattern | Warning |
|--------------|---------|
| `sl = 0` | "Zero stop loss - high risk" |
| `MagicNumber = 0` | "No magic number - position tracking issues" |
| No error handling after OrderSend | "Add return code check" |
| No IndicatorRelease in OnDeinit | "Resource leak - release handles" |
| Fixed lot size (e.g., `lot = 0.1`) | "Consider equity-based sizing" |

---

## Step 5B: Trade Validation Failure Diagnosis

### When This Triggers

Workflow status is `awaiting_ea_fix` because:
- Step 5 validation backtest returned < 50 trades
- WIDE parameters were already applied (all filters loosened)
- The EA still won't trade enough

### Workflow State Context

```python
# From runner.state
state = {
    "status": "awaiting_ea_fix",
    "fix_attempts": 1,          # Current attempt (1-3)
    "max_fix_attempts": 3,      # Maximum attempts
    "validation_trades": 11,    # Trades from last validation
    "wide_params": {...},       # The WIDE params that were used
    "ea_path": "C:/path/to/EA.mq5",
}
```

### Diagnosis Process

#### Step 1: Read the EA Source Code

Read the entire EA file and understand its trading logic:

```python
ea_path = workflow_state['ea_path']
# Read and analyze the full source code
```

#### Step 2: Identify WHY It's Not Trading

Common causes (in order of likelihood):

| Cause | Example | Diagnosis Method |
|-------|---------|------------------|
| **Hardcoded conditions** | `if(sma50 > sma200)` without param | Search for conditions without input vars |
| **Bug in entry logic** | `if(signal = true)` (assignment not comparison) | Look for logic errors |
| **Always-false condition** | `if(hour >= 8 && hour <= 6)` | Check for impossible conditions |
| **Missing trade execution** | Signal detected but no OrderSend | Trace from signal to execution |
| **Time filter too strict** | Only trades Mon 9am-10am | Check time/session filters |
| **Symbol-specific code** | `if(_Symbol == "GBPUSD")` | Search for symbol checks |
| **Timeframe-specific code** | `if(_Period != PERIOD_H1) return` | Search for period checks |
| **External dependencies** | Requires specific indicator file | Check #include statements |
| **Always-satisfied exit** | EA closes position immediately | Check exit logic |

#### Step 3: Trace the Entry Logic

1. Find `OnTick()` or main trading function
2. Trace path from entry to `OrderSend()`/`trade.Buy()`/`trade.Sell()`
3. List ALL conditions that must be true to enter
4. Identify which conditions are:
   - ✅ Controllable via input params
   - ❌ Hardcoded (need to fix)
   - ❌ Bugged (need to fix)

Example trace:
```
OnTick()
  → CheckEntryConditions()
    → condition1: sma50 > sma200  ❌ HARDCODED
    → condition2: rsi < RSILevel  ✅ param
    → condition3: spread < MaxSpread  ✅ param
    → condition4: hour >= 8  ❌ HARDCODED (should be SessionStart param)
  → ExecuteTrade()
    → trade.Buy(...)
```

### Fix Categories

#### Category A: Hardcoded Values → Add Parameters

**Problem:**
```cpp
if(sma50[1] > sma200[1])  // Hardcoded MA comparison
```

**Fix:**
```cpp
// Add input parameter
input bool UseTrendFilter = true;  // Enable SMA trend filter

// Modify condition
if(!UseTrendFilter || sma50[1] > sma200[1])
```

#### Category B: Missing Parameter Control

**Problem:**
```cpp
int maPeriod = 50;  // Fixed value in code
```

**Fix:**
```cpp
input int MA_Period = 50;  // Make configurable
```

#### Category C: Logic Bugs

**Problem:**
```cpp
if(signal = true)  // Assignment, not comparison!
```

**Fix:**
```cpp
if(signal == true)  // Or just: if(signal)
```

#### Category D: Impossible Conditions

**Problem:**
```cpp
if(hour >= 22 && hour <= 6)  // Never true!
```

**Fix:**
```cpp
if(hour >= 22 || hour <= 6)  // Night session
```

#### Category E: Missing Entry Execution

**Problem:**
```cpp
if(buySignal) {
    Print("Buy signal detected");
    // OrderSend missing!
}
```

**Fix:**
```cpp
if(buySignal) {
    Print("Buy signal detected");
    trade.Buy(lotSize, _Symbol, ask, sl, tp);
}
```

### CRITICAL: Ask Permission First

**NEVER modify the EA without user permission.**

Present findings to user:
```markdown
## EA Diagnosis: Not Trading Enough (11/50 trades)

### Root Cause Found
The EA has a **hardcoded SMA50 > SMA200 trend filter** that cannot be
disabled via parameters.

Location: Lines 454-459
```cpp
bool sma50AboveSma200 = (sma50[1] > sma200[1]);
bool trendOK = sma50AboveSma200 && closeAboveSma200;
if(!trendOK) return;  // Blocks entry
```

### Proposed Fix
Add a parameter to enable/disable the trend filter:

```cpp
input bool UseTrendFilter = true;  // Enable SMA trend filter

// In CheckEntry():
bool trendOK = !UseTrendFilter || (sma50AboveSma200 && closeAboveSma200);
```

### Impact
- Adds 1 new parameter: `UseTrendFilter`
- When false, EA trades without trend confirmation
- Original behavior preserved when true (default)

**Do you want me to apply this fix?** (Attempt 1 of 3)
- Original will be backed up to: EA_backup_20260101_143052.mq5
```

### After User Approves

1. **Backup original EA:**
```python
runner.backup_original_ea()
# Creates: EA_backup_YYYYMMDD_HHMMSS.mq5
```

2. **Apply the fix:**
Use Edit tool to modify the EA source code.

3. **Restart workflow from Step 1:**
```python
runner.restart_after_fix()
# - Recompiles modified EA
# - Re-extracts params (may have new ones)
# - Invokes /param-analyzer again (WIDE + optimization)
# - Runs validation with new WIDE params
```

### If Fix Fails (Still < 50 Trades)

Workflow returns to `awaiting_ea_fix` with `fix_attempts` incremented.

On attempts 2-3:
1. Re-read the EA (may have changed)
2. Look for OTHER causes
3. Propose different/additional fix
4. Ask permission again

After 3 failed attempts:
```markdown
## EA Fix Failed After 3 Attempts

### Attempts Made
1. Added UseTrendFilter parameter - 11 → 23 trades
2. Widened RSI threshold range - 23 → 38 trades
3. Added volatility bypass option - 38 → 47 trades

### Current Status
- 47 trades achieved (need 50)
- All obvious fixes applied

### Options
1. **Lower MIN_TRADES threshold** - Accept 47 as sufficient
2. **Manual investigation** - User reviews EA logic
3. **Abandon test** - EA may not be suitable for this backtest period

Which would you like to do?
```

### What NOT to Do

1. **Don't change core strategy logic** - Only add ON/OFF switches
2. **Don't remove safety features** - Only make them parameterizable
3. **Don't optimize FOR more trades** - Goal is to PROVE it can trade
4. **Don't modify without permission** - ALWAYS ask first
5. **Don't make assumptions** - Each EA is different, investigate thoroughly

---

## Integration with Workflow

### When invoked at Step 5B:

```python
# Workflow state
status = "awaiting_ea_fix"
fix_attempts = state.get('fix_attempts', 1)
max_attempts = state.get('max_fix_attempts', 3)

# After Claude applies fix and user approves:
runner.restart_after_fix()

# This does:
# 1. Increments version tracking
# 2. Clears old validation data
# 3. Runs from Step 1 with modified EA
# 4. New params go through /param-analyzer again
```

### Step 5B Flow Diagram

```
Step 5 FAILS (< 50 trades)
         ↓
  fix_attempts < 3?
    ├── YES → status = 'awaiting_ea_fix'
    │           ↓
    │    Claude diagnoses EA
    │           ↓
    │    Claude asks permission
    │           ↓
    │    User approves?
    │      ├── YES → Backup + Fix + restart_after_fix()
    │      │            ↓
    │      │         Step 1 (recompile)
    │      │            ↓
    │      │         ... workflow continues ...
    │      │            ↓
    │      │         Step 5 (validate again)
    │      │            ↓
    │      │         PASS? → Continue to Step 6
    │      │         FAIL? → Back to "fix_attempts < 3?"
    │      │
    │      └── NO → Report and ask what to do
    │
    └── NO (3 attempts exhausted)
            ↓
    Report failure, offer options:
    - Lower threshold
    - Manual investigation
    - Abandon test
```
