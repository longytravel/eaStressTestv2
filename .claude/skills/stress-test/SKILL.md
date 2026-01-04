# /stress-test - EA Stress Test Orchestrator

Run comprehensive stress tests on MetaTrader 5 Expert Advisors.

## Usage

```
/stress-test                    # Interactive - discover and select EA
/stress-test MyEA.mq5           # Test specific EA
/stress-test --batch            # Run in autonomous batch mode
```

## What This Does

Executes an 11-step stress testing workflow (plus optional post-step stress scenarios):

| Step | Name | Gate | Notes |
|------|------|------|-------|
| 1 | Load EA | File exists | |
| 1B | Inject OnTester | Compiles | |
| 1C | Inject Safety | Compiles | |
| 2 | Compile | No errors | If fails → /mql5-fixer |
| 3 | Extract Params | Params found | PAUSE for Step 4 |
| 4 | Analyze Params | Ranges valid | Claude /param-analyzer |
| 5 | Validate Trades | Trades >= 50 | If fails → Step 5B |
| **5B** | **Fix EA** | **Trades >= 50** | **Claude /mql5-fixer (max 3 attempts)** |
| 6 | Create INI | INI valid | |
| 7 | Run Optimization | Passes > 0 | |
| 8 | Parse Results | Robust params found | |
| 9 | Backtest Robust | PF >= 1.5, DD <= 30% | |
| 10 | Monte Carlo | Ruin <= 5%, Conf >= 70% | |
| 11 | Generate Reports | Dashboard opens | |
| 12 | Stress Scenarios (Optional) | N/A | Spread/latency scenarios + 30d tick validation |
| 13 | Forward Windows (Optional) | N/A | Time-sliced performance windows (in-sample/forward + recent windows) |
| 14 | Multi-Pair Runs (Optional) | N/A | Re-run full workflow per symbol (optimized per pair) |

## Interactive Flow

1. **Discover** - List available EAs and recent test runs
2. **Configure** - Select terminal, confirm settings
3. **Execute** - Run workflow with progress updates
4. **Review** - Show results, diagnose failures
5. **Improve** - Offer next steps (retest, improve, etc.)

## Instructions

When invoked, follow the orchestrator agent behavior defined in `.claude/agents/stress-tester.md`.

### Step 1: Discovery Phase

First, discover available resources:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from engine.terminals import TerminalRegistry
from engine.state import StateManager

# Get terminals
registry = TerminalRegistry()
terminals = registry.list_terminals()

# Get available EAs
eas = registry.find_eas()

# Get recent workflows
recent = StateManager.list_workflows()
```

Present findings to user:
- List terminals with status (ready/not found)
- List EAs sorted by modification date
- Show recent test results (passed/failed, score)

### Step 2: Configuration

After user selects EA:
1. Validate the terminal is accessible
2. Confirm symbol/timeframe (default: EURUSD H1)
3. Show backtest period (dynamic: today - 4 years)
4. Get user confirmation before proceeding

### Step 3: Workflow Execution (Phase 1)

Run the workflow which PAUSES after Step 3 for Claude analysis:

```python
from engine.runner import WorkflowRunner

def progress_callback(message):
    print(f"  {message}")

runner = WorkflowRunner(
    ea_path=selected_ea_path,
    terminal_name=selected_terminal,
    symbol='EURUSD',
    timeframe='H1',
    on_progress=progress_callback,
)

# This runs Steps 1-3 then PAUSES for Claude to analyze params
result = runner.run()  # Returns with status='awaiting_param_analysis'
```

### Step 4: Invoke /param-analyzer Skill (REQUIRED)

After Phase 1 completes, Claude MUST invoke the `/param-analyzer` skill:

```
>>> STEP 4: PARAMETER ANALYSIS
>>> Invoking /param-analyzer skill...
```

**INVOKE THE SKILL:**
```python
# Claude invokes /param-analyzer which:
# 1. Reads the EA source code
# 2. Analyzes each parameter's purpose
# 3. Generates WIDE validation params (maximize trades)
# 4. Generates OPTIMIZATION ranges (intelligent ranges)
```

The skill outputs TWO things:

**1. WIDE Validation Params** (for Step 5):
```python
wide_params = {
    "SessionStartHour": 0,      # Extended hours
    "SessionEndHour": 23,
    "MinATRPips": 0,            # Widened filters
    "MaxATRPips": 5000,
    "MaxSpreadPips": 500,
    # ... all filters loosened to maximize trades
}
```

**2. Optimization Ranges** (for Step 7):
```python
opt_ranges = [
    {"name": "StopLoss", "start": 30, "step": 10, "stop": 100, "optimize": True,
     "category": "risk", "rationale": "SL: 30-100 points"},
    {"name": "MagicNumber", "optimize": False,
     "category": "identifier", "rationale": "Never optimize"},
    # ... intelligent ranges for each param
]
```

**Continue workflow with analyzed params:**
```python
>>> Continuing with Claude-analyzed parameters...
>>> Wide params: 27 set | Optimization: 32 params
result = runner.continue_with_params(wide_params, opt_ranges)
```

### Optional: Auto-select passes (no LLM)

For unattended runs (batch / multi-pair), you can enable score-based auto selection:
- `settings.AUTO_STATS_ANALYSIS=True`
- `settings.AUTO_STATS_TOP_N=20`

This uses the same composite score as the leaderboard to pick the top passes for Step 9.

### Key Analysis Rules for Claude:

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
- Thresholds: ±30% of default

### Step 5: Validate Trades (Phase 2)

After Claude provides params, workflow continues automatically:
- Uses WIDE params for validation backtest
- Should now get 50+ trades
- If still fails → triggers Step 5B

### Step 5B: Fix EA (If Validation Fails)

When Step 5 fails (< 50 trades), the workflow PAUSES with `status='awaiting_ea_fix'`.

**Claude MUST invoke `/mql5-fixer` skill to diagnose and fix the EA:**

```
>>> STEP 5B: EA FIX REQUIRED
>>> Validation failed: 11 trades (need 50)
>>> Invoking /mql5-fixer skill to diagnose...
```

**The /mql5-fixer skill will:**
1. Read and analyze the EA source code
2. Trace entry logic to find WHY it's not trading
3. Identify hardcoded values, bugs, or overly strict conditions
4. **ASK PERMISSION** before modifying the EA
5. Backup original EA before changes
6. Apply fix and restart workflow from Step 1

**After fix is applied:**
```python
# Claude applies the fix using Edit tool, then:
runner.restart_after_fix()

# This:
# - Clears old validation data
# - Restarts from Step 1 (recompile)
# - Re-extracts params (may have new ones)
# - Invokes /param-analyzer again
# - Runs validation with new WIDE params
```

**Attempt tracking:**
```python
# State contains:
state = {
    "status": "awaiting_ea_fix",
    "fix_attempts": 1,           # Current attempt (1-3)
    "max_fix_attempts": 3,       # Maximum attempts
    "validation_trades": 11,     # Trades from last validation
}
```

**After 3 failed attempts:**
```markdown
## EA Fix Failed After 3 Attempts

### Options
1. **Lower MIN_TRADES threshold** - Accept fewer trades
2. **Manual investigation** - User reviews EA logic
3. **Abandon test** - EA may not be suitable

Which would you like to do?
```

### Step 6+: Continue with Optimization

Workflow proceeds with Claude's optimization ranges.

### Step 5: Results Presentation

After Step 11, present comprehensive results:

```python
from engine.gates import (
    check_go_live_ready,
    calculate_composite_score,
    diagnose_failure,
)

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
- All gate results with ✅/❌
- Composite score out of 10
- Edge summary (what works)
- Weaknesses list
- Dashboard path

### Step 6: Next Actions

Offer clear options:
1. **Open dashboard** - Browser opens HTML report
2. **Suggest improvements** - Invoke `/ea-improver`
3. **Test another EA** - Return to discovery
4. **Compare runs** - Show historical results
5. **Run stress scenarios** - Optional Step 12 (spread/latency/tick validation)
6. **Exit** - End session

If `AUTO_RUN_STRESS_SCENARIOS=False` in `settings.py`, you can run Step 12 after a workflow completes:

```python
from engine.runner import WorkflowRunner
runner = WorkflowRunner.from_workflow_id(workflow_id)
runner.run_stress_scenarios_only()
```

## Integration with Other Skills

### /param-analyzer
Call after extracting parameters to get intelligent ranges:
```
The EA has these parameters. Let me analyze optimal ranges...
[Invoke /param-analyzer with parameter list]
```

### /mql5-fixer
Call if compilation fails (Step 2) OR validation fails (Step 5B):

**For compilation errors:**
```
Compilation failed. Let me analyze the errors...
[Invoke /mql5-fixer with error messages]
```

**For trade validation failures:**
```
Validation failed: 11 trades (need 50). Let me diagnose the EA...
[Invoke /mql5-fixer to diagnose why EA isn't trading]
```

### /stats-analyzer
Call in Step 11 to generate insights:
```
Generating performance insights from results...
[Invoke /stats-analyzer with workflow state]
```

### /ea-improver
Call when user wants improvement suggestions:
```
Analyzing weaknesses and suggesting fixes...
[Invoke /ea-improver with stats report]
```

## Error Handling

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

Options:
1. Continue anyway (skip remaining steps)
2. Adjust parameters and retry
3. Abort test
```

## Output Files

Successful runs create:
- `runs/workflow_{ea}_{timestamp}.json` - Full state
- `runs/dashboards/{ea}_{timestamp}/index.html` - Dashboard
- `runs/dashboards/{ea}_{timestamp}/data.json` - Chart data

## Settings Reference

From `settings.py`:
- `MIN_PROFIT_FACTOR = 1.5`
- `MAX_DRAWDOWN_PCT = 30.0`
- `MIN_TRADES = 50`
- `MC_CONFIDENCE_MIN = 70.0`
- `MC_RUIN_MAX = 5.0`
- `BACKTEST_YEARS = 4`
- `DATA_MODEL = 1` (1-minute OHLC)
- `EXECUTION_LATENCY_MS = 10`
