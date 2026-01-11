---
name: stress-test
description: Run comprehensive stress tests on MetaTrader 5 Expert Advisors. Interactive workflow guide through 14 steps including compilation, parameter analysis, optimization, backtesting, and Monte Carlo simulation. Use when user wants to test an EA, run stress tests, or says /stress-test.
---

# /stress-test - EA Stress Test Orchestrator

## TWO-STAGE OPTIMIZATION FLOW

The workflow uses a two-stage optimization approach:

| Stage | Step | Purpose | Parameter Coverage |
|-------|------|---------|-------------------|
| **1. EXPLORE** | Steps 4-8 | Find what works | MAXIMUM - include all params |
| **2. REFINE** | Step 8B-8C | Narrow based on evidence | Reduced via `reopt_analyzer` |

**CRITICAL RULES:**
- Stage 1 (`/param-analyzer`) must include ALL potentially relevant parameters
- Do NOT reduce parameter ranges to hit arbitrary combination limits
- Stage 2 refinement happens ONLY after seeing actual optimization results
- The genetic optimizer is designed to handle large search spaces

---

## MANDATORY WORKFLOW STEPS (DO NOT SKIP)

| Trigger | Claude Action | Verification |
|---------|---------------|--------------|
| Step 3 completes | INVOKE `/param-analyzer` | Skill produces `wide_params` + `opt_ranges` with FULL coverage |
| After /param-analyzer | SHOW parameter review | Use `format_param_review()` helper |
| After showing review | ASK user confirmation | Wait for explicit YES |
| User confirms | CALL `continue_with_params()` | Runner validates params |
| Step 5 fails | INVOKE `/mql5-fixer` | Max 3 attempts |
| Step 8 completes | CALL `run_reopt_analysis()` | Generate analysis data - THIS is where refinement decisions happen |
| After reopt analysis | REVIEW + DECIDE | Re-optimize with refined ranges OR proceed |
| If re-optimize | ASK user confirmation | Max 2 iterations |
| After STOP 3B | INVOKE `/stats-analyzer` | Unless `AUTO_STATS_ANALYSIS=True` |
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
7. [pending] Run re-optimization analysis (STOP 3B)
8. [pending] Review analysis and make decision
9. [pending] Invoke /stats-analyzer OR confirm auto-select
10. [pending] Present results with go-live score
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

### STOP 3: Re-Optimization Analysis (After Step 8) - MANDATORY

After Step 8 completes, Claude MUST run the re-optimization analysis:

```python
# REQUIRED - runner will refuse to continue without this
analysis = runner.run_reopt_analysis()
```

**Mark todo "Run re-optimization analysis (STOP 3B)" as completed.**

---

### STOP 3B: Re-Optimization Decision (MANDATORY)

Claude MUST review the analysis and make a decision:

```python
# Get analysis data
from modules.reopt_analyzer import format_analysis_report
reopt_analysis = runner.state.get('reopt_analysis', {})
report = format_analysis_report(reopt_analysis)
print(report)

# Check iteration count
reopt_status = runner.get_reopt_status()
current_count = reopt_status['re_optimization_count']
max_allowed = reopt_status['max_iterations']  # Usually 2
```

**Review checklist:**
- [ ] Toggle analysis: Are any toggles >70% True or False in top passes?
- [ ] Continuous clustering: Are any params tightly clustered (CV < 0.20)?
- [ ] Soft recommendation: Does the auto-recommendation make sense?
- [ ] Iteration count: How many re-optimizations already done? (max 2)

**Decision matrix:**

| Condition | Decision | Action |
|-----------|----------|--------|
| Strong patterns found + count < max | RE-OPTIMIZE | Ask user, then `continue_with_refined_ranges()` |
| No strong patterns OR diversity good | PROCEED | `continue_with_analysis(selected_passes)` |
| Max iterations reached | PROCEED | Must continue, cannot re-optimize |

**If recommending RE-OPTIMIZE:**
```
Recommendation: RE-OPTIMIZE

Patterns found:
- Enable_MA_Filter: FALSE in 85% of top passes (vs 50% overall)
- RSI_Period: Clusters at 14 (CV=0.15)
- StopLoss_Points: Sweet spot at 450-600

Suggested refined ranges:
[show suggested_changes from analysis]

Re-optimization iteration: 1 of 2

Do you want to re-optimize with these refined ranges?
[Confirm] [Skip and Proceed] [Edit Ranges]
```

**If user confirms re-optimization:**
```python
# Build refined ranges from analysis suggestions
refined_ranges = build_refined_ranges(reopt_analysis)
result = runner.continue_with_refined_ranges(refined_ranges, notes="Based on reopt analysis")
# Returns to Step 6 (Create INI) -> 7 -> 8
```

**If PROCEED (no re-optimization):**
```python
# Continue to stats analysis and Step 9+
pass  # Move to next section
```

**Mark todo "Review analysis and make decision" as completed.**

---

### STOP 3C: Before Stats Analysis

```
STOP: Verify before proceeding:
[ ] Re-optimization analysis was run (STOP 3)
[ ] Decision was made at STOP 3B
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

### Phase 2: Params - Stage 1 EXPLORE (CLAUDE MUST DO)
- [ ] /param-analyzer invoked
- [ ] Wide params: ___ values
- [ ] Opt ranges: ___ optimizing, ___ fixed (FULL coverage - no artificial limits)
- [ ] User shown review table
- [ ] User confirmed: ___
- [ ] continue_with_params() called

### Phase 3: Validation
- [ ] Step 5: ___ trades (need 50)
- [ ] If failed: /mql5-fixer attempt ___/3

### Phase 3B: Stage 2 REFINE - Re-Optimization Decision (CLAUDE MUST DO)
- [ ] run_reopt_analysis() called
- [ ] Toggle analysis reviewed (which toggles won?)
- [ ] Continuous clustering reviewed (which values concentrated?)
- [ ] Soft recommendation reviewed
- [ ] Decision made: REOPTIMIZE with refined ranges / PROCEED
- [ ] If REOPTIMIZE: User confirmed modest step refinements
- [ ] If REOPTIMIZE: continue_with_refined_ranges() called
- [ ] Re-optimization iteration: ___/2

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
| 8 | Parse Results | Robust params found | PAUSE for STOP 3/3B |
| 8B | Reopt Analysis | Analysis generated | Claude runs run_reopt_analysis() |
| 8C | Reopt Decision | User decides | Claude reviews, user confirms re-opt or proceed |
| 8D | Stats Analysis | Top N selected | Claude /stats-analyzer OR auto |
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

### Parameter Analysis Rules (Stage 1 - EXPLORE)

**NEVER optimize (truly irrelevant):**
- MagicNumber, ID, identifier params
- DebugMode, logging, display params
- Safety guard params (EAStressSafety_*)

**WIDE params to maximize trades:**
- Session hours: 0-23 (trade all day)
- ATR/volatility: 1 min, 500+ max
- Spread limits: very high (100+)
- Entry requirements: loosened to minimum

**Optimization ranges - INCLUDE ALL RELEVANT PARAMS:**
- Stop loss: 50-200% of default, step 10
- Take profit: 50-300% of default, step 25
- Periods: 50-200% of default
- Thresholds: +/-30% of default
- **ALL toggles:** Test both true AND false
- **ALL filters:** Include in optimization

**DO NOT limit combinations artificially.** The genetic optimizer handles large search spaces. Refinement happens in Stage 2 (reopt_analyzer) based on actual results.

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
