# EA Stress Test System v2

Stress-test MT5 Expert Advisors through a chat-based workflow.

## Getting Started

```
1. Read this file completely
2. Check ROADMAP.md for build status
3. Run: pytest tests/ -v to verify everything works
```

## System Overview

Tests EAs through an 11-step workflow with gates at each step.

| Step | Name | Gate | Notes |
|------|------|------|-------|
| 1 | Load EA | File exists | |
| 1B | Inject OnTester | Compiles | |
| 1C | Inject Safety | Compiles | |
| 2 | Compile | No errors | If fails → /mql5-fixer |
| 3 | Extract Params | Params found | Workflow PAUSES here |
| 4 | **Analyze Params** | Ranges valid | **Claude /param-analyzer skill** |
| 5 | Validate Trades | Trades >= 50 | Uses WIDE params |
| **5B** | **Fix EA** | **Trades >= 50** | **Claude /mql5-fixer (max 3 attempts)** |
| 6 | Create INI | INI valid | Uses optimization ranges |
| 7 | Run Optimization | Passes > 0 | |
| 8 | Parse Results | Valid passes found | |
| 9 | Backtest Best | PF >= 1.5, DD <= 30% | |
| 10 | Monte Carlo | Ruin <= 5%, Conf >= 70% | |
| 11 | Generate Reports | Dashboard opens | |

### Step 4: Claude Parameter Analysis (CRITICAL)

Step 4 is handled by Claude's intelligence, NOT Python heuristics.

After Step 3, the workflow PAUSES with `status='awaiting_param_analysis'`.
Claude MUST invoke `/param-analyzer` skill which:

1. Reads the EA source code
2. Analyzes each parameter's purpose
3. Generates **WIDE validation params** (maximize trades for Step 5)
4. Generates **optimization ranges** (intelligent ranges for Step 7)

```python
# Workflow pauses after Step 3
result = runner.run()  # Returns status='awaiting_param_analysis'

# Claude invokes /param-analyzer, analyzes, then:
result = runner.continue_with_params(wide_params, opt_ranges)
```

### Step 5B: EA Fix (When Validation Fails)

If Step 5 fails (< 50 trades even with WIDE params), the workflow PAUSES with `status='awaiting_ea_fix'`.

Claude MUST invoke `/mql5-fixer` skill which:

1. Reads the EA source code
2. Traces entry logic to find WHY it's not trading
3. Identifies hardcoded values, bugs, or overly strict conditions
4. **ASKS PERMISSION** before modifying the EA
5. Backs up original EA before changes
6. Applies fix and restarts workflow from Step 1

```python
# Workflow pauses at Step 5 failure
result = runner.continue_with_params(...)  # Returns status='awaiting_ea_fix'

# State contains fix tracking:
state = {
    "status": "awaiting_ea_fix",
    "fix_attempts": 1,           # Current attempt (1-3)
    "max_fix_attempts": 3,       # Maximum attempts
    "validation_trades": 11,     # Trades from last validation
}

# After Claude applies fix (with user permission):
runner.backup_original_ea()  # Backs up to EA_backup_YYYYMMDD_HHMMSS.mq5
# Apply fix using Edit tool...
runner.restart_after_fix()   # Restarts from Step 1 with modified EA
```

**Key rules:**
- NEVER modify EA without user permission
- Original EA is backed up before any changes
- Max 3 fix attempts before giving up
- After fix, new params go through /param-analyzer again

## Critical Settings (settings.py)

```python
# Account - HARDCODED, don't change per-run
DEPOSIT = 3000
CURRENCY = "GBP"
LEVERAGE = 100

# Forward Testing
FORWARD_MODE = 2  # By date
# 3 years in-sample + 1 year forward = 4 years total

# Gates
MIN_PROFIT_FACTOR = 1.5
MAX_DRAWDOWN_PCT = 30.0
MIN_TRADES = 50
```

## Key Modules

### modules/pass_analyzer.py - THE IMPORTANT ONE
Analyzes optimization passes with proper filtering:
- Filters by minimum trades (50+)
- Extracts Forward/Back test results from each pass
- Identifies "consistent" passes (positive in BOTH periods)
- Generates composite scores

```python
from modules.pass_analyzer import analyze_passes
result = analyze_passes(optimization_results)
# Returns: filtered_passes, consistent_count, best_consistent, insights
```

### modules/stats_analyzer.py
Prepares data for Claude to analyze:
```python
from modules.stats_analyzer import prepare_analysis_data, format_for_claude
data = prepare_analysis_data("runs/workflow_xxx.json")
report = format_for_claude(data)  # Formatted text for Claude
```

### reports/workflow_dashboard.py
Generates dashboards from workflow state (even for failed EAs):
```python
from reports.workflow_dashboard import generate_dashboard_from_workflow
path = generate_dashboard_from_workflow("runs/workflow_xxx.json")
```

## Analysis Flow

1. **Optimization runs** → 8000+ passes generated
2. **pass_analyzer.py** → Filters to valid passes (50+ trades, PF > 1.0)
3. **stats_analyzer.py** → Formats data for Claude
4. **Claude analyzes** → Provides verdict, concerns, recommendations
5. **Analysis saved** → `workflow_state['claude_analysis']`
6. **Dashboard generated** → Shows Claude's analysis + all data

## Lessons Learned (READ THIS)

### 1. Don't Use "Robust Params" (Median Values)
The old approach calculated median parameter values across top passes. This creates Frankenstein parameter sets that were NEVER actually tested and often lose money.

**Instead:** Use actual best consistent pass parameters.

### 2. Forward/Back Test Results Are Critical
MT5 optimization includes `Forward Result` and `Back Result` in the params dict:
```python
params = pass_result.get('params', {})
forward = params.get('Forward Result', 0)  # 1-year forward test
back = params.get('Back Result', 0)        # 3-year back test
```

A pass is only "consistent" if BOTH are positive.

### 3. Most Passes Fail Minimum Trades
In testing, 97% of passes had < 50 trades. Filter BEFORE selecting best.

### 4. Circular Import Issues
The modules/__init__.py imports everything, causing circular imports. Use direct file imports when needed:
```python
# Instead of: from modules.pass_analyzer import analyze_passes
# Use:
import importlib.util
spec = importlib.util.spec_from_file_location("pass_analyzer", "modules/pass_analyzer.py")
```

### 5. MT5 HTML Reports Are UTF-16-LE
```python
with open(html_path, 'r', encoding='utf-16-le', errors='ignore') as f:
    content = f.read()
```

### 6. MT5 XML Uses Excel Spreadsheet ML Format
```python
rows = root.findall('.//{urn:schemas-microsoft-com:office:spreadsheet}Row')
```

### 7. Don't Auto-Add /inc: to Compiler
MetaEditor finds includes automatically when EA is in terminal's Experts folder.

## Dashboard Structure

The dashboard shows (in order):
1. **Claude's Analysis** - LLM-generated verdict and recommendations (dark section)
2. **Core Metrics** - PF, DD, trades, Sharpe, etc.
3. **Charts** - Equity curve, Monte Carlo
4. **Gates** - Pass/fail status with colors
5. **Optimization Analysis** - All valid passes with Forward/Back columns
6. **Recommended Pass** - Best consistent parameters

## File Locations

```
runs/
├── workflow_*.json              # Full workflow state
├── dashboards/{workflow_id}/    # Generated HTML dashboards
└── leaderboard/                 # Aggregated rankings

reference/
├── mql5.pdf                     # 7000-page reference
├── cache/                       # Indexed lookups (48 files)
└── lookup.py                    # Search functions
```

## Running the System

### Interactive Mode
```
/stress-test
> Select terminal: IC_Markets
> Select EA: MyEA.mq5
> Symbol: EURUSD
> Timeframe: H1
```

### Generate Dashboard for Existing Run
```python
from reports.workflow_dashboard import generate_dashboard_from_workflow
generate_dashboard_from_workflow("runs/workflow_xxx.json", open_browser=True)
```

### Analyze Optimization Results
```bash
python modules/pass_analyzer.py runs/workflow_xxx.json
```

### Regenerate Leaderboard
```python
from reports.leaderboard import generate_leaderboard
generate_leaderboard(open_browser=True)
```

## Testing

```bash
pytest tests/ -v              # All tests
pytest tests/ -v --tb=short   # Shorter output
pytest tests/test_gates.py    # Specific module
```

## What Claude Does

Claude (the LLM) provides intelligent analysis at multiple steps:

### Step 4: Parameter Analysis (`/param-analyzer` skill)
- Reads EA source code to understand each parameter
- Generates WIDE validation params (maximize trades)
- Generates intelligent optimization ranges
- NO Python heuristics - Claude's intelligence only

### Step 5B: EA Fix (`/mql5-fixer` skill)
- Triggered when validation fails (< 50 trades)
- Diagnoses WHY the EA isn't trading enough
- Identifies hardcoded values, bugs, logic errors
- **Asks permission** before modifying EA
- Backs up original and applies fix
- Max 3 attempts before giving up

### Step 11: Results Analysis (`/stats-analyzer` skill)
- Analyzes optimization results
- Provides **Verdict** (GO/NO-GO/WEAK GO)
- Identifies **Red flags**
- Makes **Parameter recommendations** based on consistency
- Suggests **Improvements**

This analysis gets saved to `workflow_state['claude_analysis']` and displayed in the dashboard.

## Don't Do This

1. Don't use hardcoded dates - calculate from TODAY
2. Don't use median/robust params - use actual best pass
3. Don't trust top passes without checking trade count
4. Don't ignore Forward/Back breakdown - it reveals curve-fitting
5. Don't generate generic placeholder text - Claude should analyze real data
6. **Don't use Python heuristics for Step 4** - Claude's /param-analyzer skill is REQUIRED
