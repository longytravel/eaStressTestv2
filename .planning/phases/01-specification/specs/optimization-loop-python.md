# Optimization Loop - Python Components

This document specifies all deterministic Python components of the optimization loop.

## 1. INI Generation

**Source:** `modules/optimizer.py` → `create_ini_file()`

### Purpose
Convert optimization ranges to MT5 INI format for the terminal.

### INI File Format

```ini
; EA Stress Test - Optimization Configuration
; Generated: 2026-01-11T14:30:00

[Tester]
Expert=MyEA.ex5
Symbol=GBPUSD
Period=60
FromDate=2022.01.11
ToDate=2026.01.11
ForwardMode=2
ForwardDate=2025.01.11
Model=1
ExecutionMode=10
Optimization=2
OptimizationCriterion=6
Report=MyEA_S7_opt_GBPUSD_H1
ReplaceReport=1
UseLocal=1
Visual=0
ShutdownTerminal=1
Deposit=3000
Currency=GBP
Leverage=100

[TesterInputs]
StopLoss=50||20||10||100||Y
TakeProfit=100||50||10||200||Y
Enable_Filter=true||true||0||true||N
```

### Parameter Line Format

```
{name}={value}||{start}||{step}||{stop}||{Y/N}
```

| Field | Description |
|-------|-------------|
| `value` | Current/default value |
| `start` | Range start |
| `step` | Step size (0 = fixed) |
| `stop` | Range end |
| `Y/N` | Y = optimize, N = fixed |

### Boolean Handling

**KNOWN BUG - FLAG FOR FIXING:**

Current code converts Python bool to MQL5 string:
```python
val = 'true' if param['fixed'] else 'false'
ini_lines.append(f'{name}={val}||{val}||0||{val}||N')
```

**Issue:** For boolean toggles with optimization (`Enable_X` with start=0, stop=1), the current code auto-detects and sets range 0-1. But when writing fixed bools, it uses 'true'/'false' strings which MT5 may not interpret correctly.

**Expected fix:** Ensure consistent boolean representation (0/1 or true/false) based on what MT5 actually accepts.

### Safety Parameter Handling

Injected safety parameters are handled specially:
- `Safety_MaxSpreadPips`: Loosened during validation (500), fixed during optimization
- `Safety_MaxSlippagePips`: Loosened during validation (500), fixed during optimization

The runner automatically:
1. Reads injected safety param names from Step 1C
2. Forces them to loose values for Step 5 (validation)
3. Forces them to fixed values for optimization/backtests

### Toggle-Dependency Rules

When a toggle is FALSE, its dependent params become irrelevant:
```
Use_RSI_Filter = false
→ RSI_Period, RSI_Overbought, RSI_Oversold are dead params
```

The INI generator does NOT handle this (it includes all params). The LLM handles this during range refinement by:
1. Identifying fixed toggles (FIX_FALSE recommendation)
2. Removing dependent params from optimization ranges

## 2. MT5 Optimization Execution

**Source:** `modules/optimizer.py` → `run_optimization()`

### Terminal Invocation

```python
terminal_exe = Path(terminal['path'])
cmd = [str(terminal_exe), f'/config:{ini_path}']
process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
```

### Timeout Handling

```python
timeout = settings.OPTIMIZATION_TIMEOUT  # 36000 seconds (10 hours)

while process.poll() is None:
    if time.time() - start_time > timeout:
        process.kill()
        return {'success': False, 'errors': [f'Optimization timed out after {timeout}s']}
```

**Note on timeout configurability:**
- Current: Fixed at 10 hours via `settings.OPTIMIZATION_TIMEOUT`
- For cloud/distributed runs, may want shorter timeouts per chunk
- For comprehensive local runs, 10 hours is appropriate

### Progress Logging

```python
progress_interval_s = 60  # Log every 60 seconds

if on_progress and (time.time() - last_progress) >= progress_interval_s:
    elapsed = time.time() - start_time
    on_progress(
        f"Optimization running: {report_name} {symbol} {timeframe} ({elapsed:.0f}s elapsed)"
    )
```

This addresses the "silent hang" problem by emitting periodic "still running" messages.

### Process Cleanup

Before starting, kills any stuck terminal/metatester processes:
```python
_terminate_terminal_processes(terminal_exe)
```

Uses `psutil` to find and kill processes matching the terminal path.

### Output Locations

MT5 writes reports to multiple locations:
- `{data_path}/` (terminal root)
- `{data_path}/Tester/`
- `{data_path}/Tester/reports/`

Report files:
- `{report_name}.xml` - Main optimization results (back/in-sample)
- `{report_name}.forward.xml` - Forward test results
- `{report_name}.htm*` - HTML report (optional)
- `{data_path}/Tester/cache/*.opt` - Optimization cache

**Deterministic report selection:**
The code uses `report_name` to find the exact report, avoiding "pick newest file" anti-pattern.

## 3. Result Parsing

**Source:** `modules/optimizer.py` → `parse_optimization_results()`

### XML Format

MT5 uses Excel Spreadsheet ML format:
```xml
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet">
  <Worksheet>
    <Table>
      <Row>
        <Cell><Data>Pass</Data></Cell>
        <Cell><Data>Result</Data></Cell>
        <Cell><Data>Profit</Data></Cell>
        ...
      </Row>
      <Row>
        <Cell><Data>1</Data></Cell>
        <Cell><Data>1234.56</Data></Cell>
        ...
      </Row>
    </Table>
  </Worksheet>
</Workbook>
```

### Pass Data Structure

After parsing and normalization:
```python
{
    'result': float,           # OnTester return value (primary sort key)
    'profit': float,           # Net profit
    'profit_factor': float,    # Gross profit / gross loss
    'expected_payoff': float,  # Average profit per trade
    'max_drawdown_pct': float, # Equity drawdown %
    'total_trades': int,       # Trade count
    'sharpe_ratio': float,     # Risk-adjusted return
    'recovery_factor': float,  # Profit / max drawdown
    'win_rate': float,         # Winning trades %
    'params': {                # EA input parameters
        'Pass': int,           # Pass number (1-indexed)
        'Forward Result': float,  # Forward test result
        'Back Result': float,     # Back test result
        'StopLoss': float,
        'TakeProfit': float,
        'Enable_Filter': bool,
        ...
    }
}
```

### Forward/Back Merge

When ForwardMode is enabled, MT5 generates two reports. The code merges them:
```python
def _merge_forward_results(base_results, forward_results):
    # Match by Pass number
    # Add forward_* prefixed metrics
    # Update total_trades to combined count
```

### Filtering

**ONTESTER_MIN_TRADES = 10:** Lower threshold for genetic exploration

```python
# In runner._step_parse_results()
# Adaptive threshold based on validation trades
base_min = settings.MIN_TRADES  # 50
validation_trades = step5_result.get('total_trades', 0)
adaptive = min(base_min, max(10, int(validation_trades * 0.8)))
```

This prevents false failures when the EA naturally produces fewer trades on certain symbols/timeframes.

## 4. All Settings (settings.py)

### Backtest Period
```python
BACKTEST_YEARS = 4       # Total period
IN_SAMPLE_YEARS = 3      # Training period
FORWARD_YEARS = 1        # Out-of-sample test
```

### Data Model
```python
DATA_MODEL = 1           # 1-minute OHLC (Model=0 for every tick)
EXECUTION_LATENCY_MS = 10  # 10ms execution delay
```

### Account
```python
DEPOSIT = 3000
CURRENCY = "GBP"
LEVERAGE = 100
```

### Gates/Thresholds
```python
MIN_PROFIT_FACTOR = 1.5
MAX_DRAWDOWN_PCT = 30.0
MIN_TRADES = 50          # Final gate threshold
ONTESTER_MIN_TRADES = 10 # Lower for genetic exploration
```

### Timeouts
```python
OPTIMIZATION_TIMEOUT = 36000  # 10 hours
```

**Configurability note:** For cloud/distributed systems, this should be parameterizable:
- Short timeout per worker (e.g., 30 min)
- Aggregation of results across workers
- Currently: Single-machine focus, 10 hours is appropriate

### Optimization Settings
```python
OPTIMIZATION_CRITERION = 6     # Custom (OnTester return)
MAX_OPTIMIZATION_PASSES = 1000 # Max passes to keep
TOP_PASSES_DISPLAY = 20        # Show in dashboard
TOP_PASSES_BACKTEST = 30       # Detailed analysis
```

### Re-Optimization Thresholds
```python
REOPT_TOGGLE_THRESHOLD = 0.70       # 70% = strong pattern
REOPT_CLUSTERING_CV_THRESHOLD = 0.20  # CV < 0.2 = tight
REOPT_MIN_VALID_PASSES = 50         # Suggest widening if fewer
REOPT_MAX_ITERATIONS = 2            # HARD LIMIT
```

### Go Live Score
```python
GO_LIVE_SCORE_WEIGHTS = {
    'consistency': 0.25,      # Both back+forward positive
    'total_profit': 0.25,     # Actual money made
    'trade_count': 0.20,      # Statistical confidence
    'profit_factor': 0.15,    # Edge quality
    'max_drawdown': 0.15,     # Risk (inverted)
}

GO_LIVE_SCORE_RANGES = {
    'total_profit': (0, 5000),
    'trade_count': (50, 200),
    'profit_factor': (1.0, 3.0),
    'max_drawdown': (0, 30),
    'consistency_min': (0, 2000),
}
```

### Automation
```python
AUTO_STATS_ANALYSIS = True   # Use score-based selection
AUTO_STATS_TOP_N = 20        # Select top 20 passes
```

## 5. Parameter Importance Analysis

**Source:** `modules/reopt_analyzer.py`

This module provides deterministic statistical analysis for LLM interpretation.

### Toggle Analysis

For each boolean/toggle parameter:
```python
@dataclass
class ToggleAnalysis:
    name: str
    top_true_count: int       # Count of True in top N
    top_false_count: int      # Count of False in top N
    top_true_pct: float       # % True in top N
    all_true_count: int       # Count of True in all passes
    all_true_pct: float       # % True in all passes
    top_vs_all_diff: float    # Difference (positive = True helps)
    avg_score_true: float     # Average score when True
    avg_score_false: float    # Average score when False
    recommendation: str       # FIX_TRUE, FIX_FALSE, KEEP_OPTIMIZING
```

**Pattern detection:**
- If ≥70% of top passes have same value → strong pattern
- `FIX_TRUE`: 70%+ of top passes have True
- `FIX_FALSE`: 70%+ of top passes have False
- `KEEP_OPTIMIZING`: No clear winner

### Continuous Analysis

For each numeric parameter:
```python
@dataclass
class ContinuousAnalysis:
    name: str
    original_range: dict      # {start, stop, step}
    top_values: list          # Values in top N passes
    top_mean: float
    top_std: float
    top_min: float
    top_max: float
    coefficient_of_variation: float  # std/mean (lower = tighter)
    range_utilization: dict   # {value: {count, avg_score}}
    suggested_refined_range: dict
    recommendation: str       # NARROW_RANGE, WIDEN_RANGE, KEEP_RANGE
```

**Clustering detection:**
- CV < 0.20 = tight clustering → recommend narrowing
- Only 1-2 values used → recommend widening
- Otherwise → keep current range

### Output Format

```python
@dataclass
class ReoptAnalysis:
    total_passes: int
    valid_passes: int
    top_n_analyzed: int
    toggle_analysis: dict     # {param_name: ToggleAnalysis}
    continuous_analysis: dict # {param_name: ContinuousAnalysis}
    recommendation: ReoptRecommendation
    patterns_summary: list    # Human-readable patterns
```

**Recommendation structure:**
```python
@dataclass
class ReoptRecommendation:
    should_reoptimize: bool
    confidence: str           # low, medium, high
    reasons: list             # Why this recommendation
    suggested_changes: list   # Specific param changes
```

### Example Output

```
============================================================
RE-OPTIMIZATION ANALYSIS
============================================================

Total Passes: 5000
Valid Passes: 1234
Top N Analyzed: 20

------------------------------------------------------------
RECOMMENDATION
------------------------------------------------------------
Should Re-optimize: YES
Confidence: MEDIUM

Reasons:
  • Use_RSI_Filter=False in 85% of top passes (vs 50% overall)
  • TakeProfit clusters tightly around 150.0 (CV=0.15)

Suggested Changes:
  • Use_RSI_Filter: Fix to False
  • TakeProfit: Narrow to 120-180 step 5

------------------------------------------------------------
PATTERNS FOUND
------------------------------------------------------------
• Use_RSI_Filter: False wins (85% in top, avg score 7.2 vs 5.1)
• TakeProfit: Clusters at 150.0 (range 120-180, CV=0.15)
```

This analysis is provided to the LLM for interpretation and decision-making.
