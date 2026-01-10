---
name: stress-test
description: Run comprehensive stress tests on MetaTrader 5 Expert Advisors. Interactive workflow guide through 14 steps including compilation, parameter analysis, optimization, backtesting, and Monte Carlo simulation. Use when user wants to test an EA, run stress tests, or says /stress-test.
---

# /stress-test - EA Stress Test Orchestrator

## MANDATORY WORKFLOW STEPS (DO NOT SKIP)

| Trigger | Claude Action | Verification |
|---------|---------------|--------------|
| Step 3 completes | INVOKE `/param-analyzer` | Skill produces `wide_params` + `opt_ranges` |
| After /param-analyzer | SHOW parameter review | Use `format_param_review()` helper |
| After showing review | ASK user confirmation | Wait for explicit YES |
| User confirms | CALL `continue_with_params()` | Runner validates params |
| Step 5 fails | INVOKE `/mql5-fixer` | Max 3 attempts |
| Step 8 completes | INVOKE `/stats-analyzer` | Unless `AUTO_STATS_ANALYSIS=True` |
| Workflow ends | PRESENT results | Show go-live score + dashboard path |

---

## TODOWRITE: Create These Todos When Skill Starts

When `/stress-test` is invoked, **immediately create these todos**:

```
1. [in_progress] Run Phase 1 (Steps 1-3)
2. [pending] Invoke /param-analyzer skill
3. [pending] Show parameter review to user
4. [pending] Get user confirmation on params
5. [pending] Call continue_with_params()
6. [pending] Handle Step 5 result (pass or fix)
7. [pending] Invoke /stats-analyzer OR confirm auto-select
8. [pending] Present results with go-live score
```

Mark each as `completed` when done. Mark as `in_progress` when starting.

---

## WORKFLOW FLOW

### Phase 1: Discovery & Execution (Steps 1-3)

```python
from engine.runner import WorkflowRunner
from engine.terminals import TerminalRegistry

# Discover available EAs
registry = TerminalRegistry()
eas = registry.find_eas()

# Run workflow - PAUSES after Step 3
runner = WorkflowRunner(ea_path, terminal_name, symbol='EURUSD', timeframe='H1')
result = runner.run()  # Returns status='awaiting_param_analysis'
```

**Mark todo "Run Phase 1" as completed.**

---

### STOP 1: Before Parameter Analysis

```
STOP: Phase 1 complete. Before continuing:
[ ] Status is 'awaiting_param_analysis'
[ ] Parameters were extracted (check result)

Now INVOKE /param-analyzer skill.
```

---

### Phase 2: Parameter Analysis (Step 4)

**Mark todo "Invoke /param-analyzer" as in_progress.**

INVOKE the `/param-analyzer` skill. It will:
1. Read the EA source code
2. Analyze each parameter's purpose
3. Generate `wide_params` (maximize trades)
4. Generate `opt_ranges` (optimization ranges)

**Mark todo "Invoke /param-analyzer" as completed.**

---

### STOP 2: Before continue_with_params()

```
STOP: Verify before proceeding:
[ ] /param-analyzer was invoked (not skipped)
[ ] format_param_review() output shown to user
[ ] User explicitly confirmed "yes" or "proceed"

DO NOT call continue_with_params() until ALL checked.
```

**Show parameter review:**

```python
review = WorkflowRunner.format_param_review(wide_params, opt_ranges)
print(review['summary_text'])
```

**Mark todo "Show parameter review" as completed.**

**Ask user:**
```
Do you want to proceed with these parameters?
[Confirm] [Edit Ranges] [Cancel]
```

**Mark todo "Get user confirmation" as completed** only after explicit YES.

**Continue workflow:**

```python
result = runner.continue_with_params(wide_params, opt_ranges)
```

**Mark todo "Call continue_with_params()" as completed.**

---

### Phase 3: Validation (Step 5)

If Step 5 passes (50+ trades): Continue to Phase 4.

If Step 5 fails (< 50 trades):
1. Status becomes `awaiting_ea_fix`
2. INVOKE `/mql5-fixer` skill
3. After fix: `runner.restart_after_fix()`
4. Max 3 attempts

**Mark todo "Handle Step 5 result" as completed.**

---

### STOP 3: Before Stats Analysis (After Step 8)

```
STOP: Verify before proceeding:
[ ] Optimization completed (Step 8)
[ ] Either:
    - /stats-analyzer invoked, OR
    - AUTO_STATS_ANALYSIS=True in settings

DO NOT call continue_with_analysis() until checked.
```

If `AUTO_STATS_ANALYSIS=True`: Runner auto-selects top 20 passes.

Otherwise: INVOKE `/stats-analyzer` skill to select passes.

**Mark todo "Invoke /stats-analyzer OR confirm auto-select" as completed.**

---

### Phase 4: Results Presentation (After Step 11)

```python
from engine.gates import check_go_live_ready, calculate_composite_score

state_dict = runner.state.to_dict()
go_live = check_go_live_ready(state_dict)
score = calculate_composite_score(state_dict.get('metrics', {}))
```

**Present to user:**
- Go-live score: X/10
- PASS/FAIL verdict
- Gate results with checkmarks
- Dashboard path
- Next steps (improve, retest, compare)

**Mark todo "Present results with go-live score" as completed.**

---

### STOP 4: Before Ending Session

```
STOP: Verify before ending:
[ ] Go-live score calculated and shown
[ ] Dashboard path provided
[ ] Next steps offered (improve, retest, compare)

DO NOT end workflow presentation without ALL checked.
```

---

## CHECKLIST TEMPLATE

Copy this for each run:

```markdown
## Stress Test: [EA_NAME] | [SYMBOL] | [DATE]

### Phase 1: Preparation
- [ ] Steps 1-3 complete, status=awaiting_param_analysis

### Phase 2: Params (CLAUDE MUST DO)
- [ ] /param-analyzer invoked
- [ ] Wide params: ___ values
- [ ] Opt ranges: ___ optimizing, ___ fixed
- [ ] User shown review table
- [ ] User confirmed: ___
- [ ] continue_with_params() called

### Phase 3: Validation
- [ ] Step 5: ___ trades (need 50)
- [ ] If failed: /mql5-fixer attempt ___/3

### Phase 4: Optimization (CLAUDE MUST DO)
- [ ] Step 8: ___ passes found
- [ ] /stats-analyzer invoked OR auto-select: ___
- [ ] Top 20 selected

### Phase 5: Results (CLAUDE MUST DO)
- [ ] Go-live score: ___/10
- [ ] Dashboard shown: ___
- [ ] Next steps offered: ___
```

---

## REFERENCE: Step Details

### Step Overview

| Step | Name | Gate | Notes |
|------|------|------|-------|
| 1 | Load EA | File exists | |
| 1B | Inject OnTester | Compiles | |
| 1C | Inject Safety | Compiles | |
| 2 | Compile | No errors | If fails: /mql5-fixer |
| 3 | Extract Params | Params found | PAUSE for Step 4 |
| 4 | Analyze Params | Ranges valid | Claude /param-analyzer |
| 4B | Parameter Review | User confirms | Show all params, get confirmation |
| 5 | Validate Trades | Trades >= 50 | If fails: Step 5B |
| 5B | Fix EA | Trades >= 50 | Claude /mql5-fixer (max 3 attempts) |
| 6 | Create INI | INI valid | |
| 7 | Run Optimization | Passes > 0 | |
| 8 | Parse Results | Robust params found | |
| 9 | Backtest Robust | PF >= 1.5, DD <= 30% | |
| 10 | Monte Carlo | Ruin <= 5%, Conf >= 70% | |
| 11 | Generate Reports | Dashboard opens | |
| 12 | Stress Scenarios | Optional | Spread/latency + tick validation |
| 13 | Forward Windows | Optional | Time-sliced performance windows |
| 14 | Multi-Pair Runs | Optional | Re-run per symbol |

### Usage

```
/stress-test                    # Interactive - discover and select EA
/stress-test MyEA.mq5           # Test specific EA
/stress-test --batch            # Run in autonomous batch mode
```

### Discovery Phase

```python
from engine.terminals import TerminalRegistry
from engine.state import StateManager

registry = TerminalRegistry()
terminals = registry.list_terminals()
eas = registry.find_eas()
recent = StateManager.list_workflows()
```

### Configuration

After user selects EA:
1. Validate terminal is accessible
2. Confirm symbol/timeframe (default: EURUSD H1)
3. Show backtest period (dynamic: today - 4 years)
4. Get user confirmation

### Parameter Analysis Rules

**NEVER optimize:**
- MagicNumber, ID, identifier params
- DebugMode, logging, display params
- Safety guard params (EAStressSafety_*)

**WIDE params to maximize trades:**
- Session hours: 0-23 (trade all day)
- ATR/volatility: 1 min, 500+ max
- Spread limits: very high (100+)
- Entry requirements: loosened to minimum

**Optimization ranges:**
- Stop loss: 50-200% of default, step 10
- Take profit: 50-300% of default, step 25
- Periods: 50-200% of default
- Thresholds: +/-30% of default

### Step 5B: Fix EA (If Validation Fails)

When Step 5 fails (< 50 trades), status becomes `awaiting_ea_fix`.

The /mql5-fixer skill will:
1. Read and analyze the EA source code
2. Trace entry logic to find WHY it's not trading
3. Identify hardcoded values, bugs, or overly strict conditions
4. ASK PERMISSION before modifying the EA
5. Backup original EA before changes
6. Apply fix and restart workflow

After fix:
```python
runner.restart_after_fix()
```

After 3 failed attempts, offer options:
1. Lower MIN_TRADES threshold
2. Manual investigation
3. Abandon test

### Auto-Select Passes (No LLM)

For unattended runs:
- `settings.AUTO_STATS_ANALYSIS=True`
- `settings.AUTO_STATS_TOP_N=20`

Uses composite score to pick top passes for Step 9.

### Results Presentation

```python
from engine.gates import check_go_live_ready, calculate_composite_score, diagnose_failure

state_dict = runner.state.to_dict()
go_live = check_go_live_ready(state_dict)
score = calculate_composite_score(state_dict.get('metrics', {}))

if not go_live['go_live_ready']:
    diagnoses = diagnose_failure(
        state_dict.get('gates', {}),
        state_dict.get('metrics', {}),
    )
```

Format output with:
- Clear PASS/FAIL verdict
- All gate results with checkmarks
- Composite score out of 10
- Edge summary (what works)
- Weaknesses list
- Dashboard path

### Next Actions

Offer options:
1. Open dashboard - Browser opens HTML report
2. Suggest improvements - Invoke /ea-improver
3. Test another EA - Return to discovery
4. Compare runs - Show historical results
5. Run stress scenarios - Optional Step 12
6. Exit - End session

### Run Stress Scenarios Post-Hoc

```python
runner = WorkflowRunner.from_workflow_id(workflow_id)
runner.run_stress_scenarios_only()
```

### Integration with Other Skills

- `/param-analyzer` - After Step 3, generate params
- `/mql5-fixer` - Step 2 compilation errors OR Step 5B validation failures
- `/stats-analyzer` - After Step 8, select top passes
- `/ea-improver` - After results, suggest improvements

### Error Handling

**Terminal not found:**
```
Terminal 'IC_Markets' not found at configured path.
Please check terminals.json configuration.
```

**EA not found:**
```
EA 'MyEA.mq5' not found in Experts folder.
Available EAs: [list]
```

**Compilation error:**
```
Compilation failed with [N] errors:
[Show errors]

Would you like me to try fixing these? [Y/n]
[If yes, invoke /mql5-fixer]
```

**Gate failure:**
```
Step [N] failed: [Gate name]
Value: [actual] (required: [threshold])

Diagnosis: [Why this happened]
Suggestion: [What to do about it]
```

### Output Files

Successful runs create:
- `runs/workflow_{ea}_{timestamp}.json` - Full state
- `runs/dashboards/{ea}_{timestamp}/index.html` - Dashboard
- `runs/dashboards/{ea}_{timestamp}/data.json` - Chart data

### Settings Reference

From `settings.py`:
- `MIN_PROFIT_FACTOR = 1.5`
- `MAX_DRAWDOWN_PCT = 30.0`
- `MIN_TRADES = 50`
- `MC_CONFIDENCE_MIN = 70.0`
- `MC_RUIN_MAX = 5.0`
- `BACKTEST_YEARS = 4`
- `DATA_MODEL = 1` (1-minute OHLC)
- `EXECUTION_LATENCY_MS = 10`
