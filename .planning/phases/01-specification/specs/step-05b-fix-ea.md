# Step 5B: Fix EA

**Status:** Workflow pause point (conditional)
**Skill Integration:** `/mql5-fixer` (required)
**Gate:** Same as Step 5 — MIN_TRADES threshold
**Max Attempts:** 3 (configurable)

---

## Overview

Step 5B triggers when the validation backtest (Step 5) produces fewer than MIN_TRADES. The workflow pauses and waits for the `/mql5-fixer` skill to diagnose WHY the EA isn't trading enough and propose fixes.

This is a RETRY LOOP — after each fix attempt:
1. EA is modified (with permission)
2. Workflow restarts from Step 1
3. Re-compiles, re-extracts params, re-runs /param-analyzer
4. Step 5 validation runs again

Maximum 3 attempts before workflow fails.

---

## Trigger Condition

Step 5B activates when:
```python
# Code reference: engine/runner.py:830-843

if not passed:  # Step 5 validation failed
    if self.fix_attempts < self.max_fix_attempts:
        self.fix_attempts += 1
        self.state.set('fix_attempts', self.fix_attempts)
        self.state.set('max_fix_attempts', self.max_fix_attempts)
        self.state.set_status('awaiting_ea_fix')
```

---

## Inputs

### Workflow State
```python
state = {
    "status": "awaiting_ea_fix",
    "fix_attempts": 1,              # Current attempt (1-3)
    "max_fix_attempts": 3,          # Maximum attempts allowed
    "ea_path": "C:/path/to/EA.mq5", # Original EA path
    "steps": {
        "5_validate_trades": {
            "passed": False,
            "result": {
                "total_trades": 11,  # Below MIN_TRADES
                "gate": {
                    "passed": False,
                    "value": 11,
                    "threshold": 50,
                }
            }
        }
    }
}
```

### From Step 4
```python
wide_validation_params: dict  # The WIDE params that were used
# Important: If wide params produced few trades, the problem is
# likely hardcoded logic, not parameter settings
```

---

## Process

### 1. Diagnose the Problem

The `/mql5-fixer` skill must:

1. **Read the full EA source code**
2. **Trace entry logic** from OnTick() to OrderSend()
3. **Identify blocking conditions:**
   - Hardcoded values that can't be overridden
   - Logic bugs (assignment instead of comparison)
   - Impossible conditions (hour >= 22 AND hour <= 6)
   - Missing trade execution code
   - Symbol/timeframe restrictions

### 2. Present Findings

**CRITICAL:** Always ask permission before modifying the EA.

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

### 3. Apply Fix (After Approval)

1. **Backup original EA:**
```python
runner.backup_original_ea()
# Creates: EA_backup_YYYYMMDD_HHMMSS.mq5
```

2. **Modify EA source** using Edit tool

3. **Restart workflow:**
```python
runner.restart_after_fix()
# This:
# - Increments version tracking
# - Clears old validation data
# - Runs from Step 1 with modified EA
# - New params go through /param-analyzer again
```

---

## Fix Categories

### Category A: Hardcoded Values → Add Parameters

**Problem:**
```cpp
if(sma50[1] > sma200[1])  // Hardcoded MA comparison
```

**Fix:**
```cpp
input bool UseTrendFilter = true;

// Modify condition
if(!UseTrendFilter || sma50[1] > sma200[1])
```

### Category B: Missing Parameter Control

**Problem:**
```cpp
int maPeriod = 50;  // Fixed value in code
```

**Fix:**
```cpp
input int MA_Period = 50;  // Make configurable
```

### Category C: Logic Bugs

**Problem:**
```cpp
if(signal = true)  // Assignment, not comparison!
```

**Fix:**
```cpp
if(signal == true)  // Or just: if(signal)
```

### Category D: Impossible Conditions

**Problem:**
```cpp
if(hour >= 22 && hour <= 6)  // Never true!
```

**Fix:**
```cpp
if(hour >= 22 || hour <= 6)  // Night session
```

### Category E: Missing Entry Execution

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

---

## Retry Mechanism

### Fix Tracking
```python
# Code reference: engine/runner.py:834-837

self.fix_attempts += 1
self.state.set('fix_attempts', self.fix_attempts)
self.state.set('max_fix_attempts', self.max_fix_attempts)  # Default: 3
self.state.set_status('awaiting_ea_fix')
```

### After Each Fix
```python
# Code reference: engine/runner.py:1321-1359

def restart_with_improved_ea(self) -> 'WorkflowRunner':
    """Start fresh workflow with improved EA after fix."""
    # Store reference to previous workflow
    previous_workflow_id = self.state.workflow_id

    # Create new runner for the modified EA
    new_runner = WorkflowRunner(
        ea_path=str(self.ea_path),  # Same path, modified content
        terminal_name=self.terminal['name'],
        symbol=self.symbol,
        timeframe=self.timeframe,
    )

    # Link to previous workflow for comparison
    new_runner.previous_workflow_id = previous_workflow_id
    new_runner.state.set('previous_workflow_id', previous_workflow_id)
    new_runner.state.set('improvement_run', True)

    return new_runner
```

### Max Attempts Reached
```python
# Code reference: engine/runner.py:844-847

else:
    self._log(f"Max fix attempts ({self.max_fix_attempts}) reached - workflow failed")
    self.state.complete_workflow(False)
    return self.state.get_summary()
```

---

## Flow Diagram

```
Step 5 FAILS (< 50 trades)
         │
         ▼
  fix_attempts < 3?
    ├── YES → status = 'awaiting_ea_fix'
    │           │
    │           ▼
    │    /mql5-fixer diagnoses EA
    │           │
    │           ▼
    │    Claude asks permission
    │           │
    │      User approves?
    │        ├── YES → Backup + Fix + restart
    │        │           │
    │        │           ▼
    │        │         Step 1 (recompile)
    │        │           │
    │        │           ▼
    │        │         Step 3 (extract params)
    │        │           │
    │        │           ▼
    │        │         Step 4 (/param-analyzer)
    │        │           │
    │        │           ▼
    │        │         Step 5 (validate again)
    │        │           │
    │        │         PASS? → Continue to Step 6
    │        │         FAIL? → Back to "fix_attempts < 3?"
    │        │
    │        └── NO → Report and ask what to do
    │
    └── NO (3 attempts exhausted)
            │
            ▼
    Report failure, offer options:
    - Lower MIN_TRADES threshold
    - Manual investigation
    - Abandon test
```

---

## Gate

Same gate as Step 5:

**Name:** `minimum_trades`
**Threshold:** `settings.MIN_TRADES` (default: 50)
**Operator:** `>=`

Gate is re-checked after each fix attempt during Step 5 re-run.

---

## Skill Integration: /mql5-fixer

### Trigger
- Workflow status is `awaiting_ea_fix`
- User invokes `/mql5-fixer`
- Automatically invoked after Step 5 failure

### Input to Skill
```python
{
    "status": "awaiting_ea_fix",
    "fix_attempts": N,           # Current attempt number
    "max_fix_attempts": 3,
    "ea_path": str,             # Path to EA source
    "validation_trades": int,   # Trades from last validation
    "wide_params": dict,        # Wide params that were used
}
```

### Skill Responsibilities
1. Read and understand the full EA source
2. Trace entry logic to identify blocking conditions
3. Diagnose root cause of low trade count
4. Present findings with exact code locations
5. Propose minimal fix (add toggle, not change strategy)
6. Ask permission before modifying
7. Backup original EA
8. Apply fix and restart workflow

### What NOT to Do
- Don't change core strategy logic — only add ON/OFF switches
- Don't remove safety features — only make them parameterizable
- Don't optimize FOR more trades — goal is to PROVE it can trade
- Don't modify without permission — ALWAYS ask first

See: `.claude/skills/mql5-fixer/SKILL.md`

---

## Prerequisite for Optimization Loop

**Critical Understanding:**

If the EA still doesn't trade after Step 5B fixes (3 attempts), the problem is FUNDAMENTAL. The `/optimization-loop` skill expects a trading EA.

The optimization loop cannot fix an EA that fundamentally cannot trade. Step 5B must resolve trade execution issues before optimization begins.

Handoff requirements:
- EA produces ≥ MIN_TRADES with wide params
- All blocking conditions either removed or parameterized
- Ready for comprehensive parameter exploration

---

## Implementation Notes

### Code References
- `engine/runner.py:830-847` — Step 5 failure handling
- `engine/runner.py:1321-1359` — `restart_with_improved_ea()` method
- `engine/runner.py:1417-1420` — Fix attempt tracking in state

### State Management
```python
# Fix tracking fields
state.fix_attempts: int           # Current attempt (1-3)
state.max_fix_attempts: int       # Maximum (default: 3)
state.original_ea_backup: str     # Path to backup file
```

### Backup Strategy
Original EA is backed up before first modification:
```
EA.mq5 → EA_backup_YYYYMMDD_HHMMSS.mq5
```

Backup is preserved through all fix attempts. User can always restore original.

---

*Spec version: 1.0*
*Last updated: 2026-01-11*
