# Step 9: Backtest Top Passes

**Status:** Automatic step
**Gate:** Per-pass gates (profit_factor, max_drawdown, minimum_trades)
**Input:** Selected passes from Step 8B (top N by score or profit)

---

## Overview

Step 9 runs full 4-year backtests on each of the top passes selected in Step 8B. This produces:
- Actual equity curves (not just optimization summary stats)
- Per-trade data for Monte Carlo simulation
- Validated metrics with extended statistics
- In-sample vs forward split profits

The **best pass** (by score or profit, configurable) becomes the workflow's headline result and feeds into Step 10 (Monte Carlo).

---

## Inputs

### From Step 8B (Select Passes)
```python
top_passes: list[dict]
# Each pass contains:
{
    'pass': int,                    # Pass number from optimization
    'params': {
        'Pass': int,
        'Forward Result': float,    # Forward period profit
        'Back Result': float,       # In-sample period profit
        'Result': float,            # Combined metric
        'Custom': float,            # OnTester return value
        # ... all EA input parameters ...
    },
    'profit': float,
    'profit_factor': float,
    'max_drawdown_pct': float,
    'total_trades': int,
}
```

### From Previous Steps
```python
compiled_ea_path: str   # Path to compiled .ex5 file
symbol: str             # Trading symbol
timeframe: str          # Timeframe
terminal: dict          # Terminal configuration
fixed_params: dict      # Injected safety params to override
```

---

## Process

### 1. Prepare Parameters

For each pass, extract input parameters and add fixed safety params:

```python
# Code reference: engine/runner.py:1700-1709

RESULT_FIELDS = {'Pass', 'Forward Result', 'Back Result', 'Custom', 'Result'}

for pass_data in top_passes:
    params = pass_data.get('params', {})

    # Filter out result fields, keep only input params
    input_params = {k: v for k, v in params.items() if k not in RESULT_FIELDS}

    # Add fixed params (must override to disable broken features)
    input_params.update(fixed_params)
```

### 2. Run Backtest Per Pass

```python
# Code reference: engine/runner.py:1711-1722

report_name = self._make_report_name('S9_bt', f'pass{pass_num}')

result = run_backtest(
    self.compiled_ea_path,
    symbol=self.symbol,
    timeframe=self.timeframe,
    params=input_params,
    report_name=report_name,           # Deterministic naming!
    terminal=self.terminal,
    on_progress=self._log,
    progress_interval_s=60,
)
```

**Deterministic Report Naming:** Uses `_make_report_name()` to avoid report collisions:
```python
report_name = f'S9_bt_pass{pass_num}_{symbol}_{timeframe}_{timestamp}'
```

### 3. Calculate Composite Score

```python
# Code reference: engine/runner.py:1731-1761

score_metrics = {
    'profit': result.get('profit', 0),
    'total_trades': result.get('total_trades', 0),
    'profit_factor': result.get('profit_factor', 0),
    'max_drawdown_pct': result.get('max_drawdown_pct', 0),
    'forward_result': params.get('Forward Result', 0),
    'back_result': params.get('Back Result', 0),
}

score = gates.calculate_composite_score(score_metrics)

# Bonus for positive forward/back optimization results
if result.get('forward_result', 0) > 0 and result.get('back_result', 0) > 0:
    score = min(10, score + 0.5)

result['composite_score'] = score
result['is_consistent'] = is_consistent
```

### 4. Select Best Pass

```python
# Code reference: engine/runner.py:1772-1779

selection_metric = getattr(settings, 'BEST_PASS_SELECTION', 'score')

# Track best for Monte Carlo
if selection_metric == 'profit':
    candidate = (profit, score)
else:  # 'score' (default)
    candidate = (score, profit)

if candidate > best_candidate:
    best_candidate = candidate
    best_result = result
```

---

## Backtest Details

### Parameters Applied
- **Input params:** Extracted from optimization pass (filtered)
- **Fixed params:** Injected safety overrides (MaxSpreadPips, MaxSlippagePips)
- **Period:** Same as optimization (4 years: 3 in-sample + 1 forward)
- **Model:** 1-minute OHLC (DATA_MODEL=1)
- **Latency:** 10ms (EXECUTION_LATENCY_MS=10)

### Trade Extraction

The backtest module extracts per-trade data for equity curves and Monte Carlo:

```python
# Code reference: modules/backtest.py:370-456

from modules.trade_extractor import (
    extract_trades,
    compute_equity_curve,
    generate_chart_data,
    split_trades_by_date,
)

trades_result = extract_trades(str(report_path))
if trades_result.success and trades_result.trades:
    equity = compute_equity_curve(trades_result.trades, trades_result.initial_balance)
    result['equity_curve'] = equity
    result['trade_count'] = len(trades_result.trades)
    result['charts'] = generate_chart_data(trades_result.trades)

    # Split in-sample vs forward based on split date
    before_trades, after_trades = split_trades_by_date(trades_result.trades, split_dt)

    result['equity_curve_in_sample'] = compute_equity_curve(before_trades, initial_balance)
    result['equity_curve_forward'] = compute_equity_curve(after_trades, forward_start_balance)
    result['split_profit_in_sample'] = sum(t.net_profit for t in before_trades)
    result['split_profit_forward'] = sum(t.net_profit for t in after_trades)
```

---

## Trade Data Structure

```python
# Code reference: modules/trade_extractor.py:15-46

@dataclass
class Trade:
    ticket: int
    symbol: str
    trade_type: str          # 'buy' or 'sell'
    volume: float
    open_time: datetime
    close_time: datetime
    open_price: float
    close_price: float
    commission: float = 0.0
    swap: float = 0.0
    gross_profit: float = 0.0
    net_profit: float = 0.0  # gross_profit + commission + swap
    mfe: float = 0.0         # Maximum Favorable Excursion
    mae: float = 0.0         # Maximum Adverse Excursion
    holding_seconds: int = 0
```

---

## Gates

### Per-Pass Gate Check

```python
# Code reference: engine/gates.py:240-261

def check_all_backtest_gates(results: dict) -> dict:
    pf = results.get('profit_factor', 0)
    dd = results.get('max_drawdown_pct', 100)
    trades = results.get('total_trades', 0)

    gates = {
        'profit_factor': check_profit_factor(pf),
        'max_drawdown': check_max_drawdown(dd),
        'minimum_trades': check_minimum_trades(trades),
    }

    all_passed = all(g.passed for g in gates.values())
    return {'all_passed': all_passed, 'gates': {...}}
```

### Individual Gate Functions

```python
# Code reference: engine/gates.py:163-184

def check_profit_factor(pf: float) -> GateResult:
    passed = pf >= settings.MIN_PROFIT_FACTOR  # Default: 1.5
    return GateResult(name='profit_factor', passed=passed, value=pf, threshold=settings.MIN_PROFIT_FACTOR, operator='>=')

def check_max_drawdown(dd_pct: float) -> GateResult:
    passed = dd_pct <= settings.MAX_DRAWDOWN_PCT  # Default: 30%
    return GateResult(name='max_drawdown', passed=passed, value=dd_pct, threshold=settings.MAX_DRAWDOWN_PCT, operator='<=')

def check_minimum_trades(total_trades: int) -> GateResult:
    passed = total_trades >= settings.MIN_TRADES  # Default: 50
    return GateResult(name='minimum_trades', passed=passed, value=total_trades, threshold=settings.MIN_TRADES, operator='>=')
```

---

## Settings Reference

```python
# Code reference: settings.py

# Gate thresholds
MIN_PROFIT_FACTOR = 1.5         # Minimum profit factor
MAX_DRAWDOWN_PCT = 30.0         # Maximum drawdown percentage
MIN_TRADES = 50                 # Minimum trades for significance

# Best pass selection
BEST_PASS_SELECTION = "score"   # "score" (default) or "profit"

# How many passes to backtest
TOP_PASSES_BACKTEST = 30        # Top N passes for detailed analysis
```

---

## Outputs

### Per-Pass Result

```python
result = {
    'success': True,
    'pass_num': int,
    'input_params': dict,              # Parameters used
    'profit': float,
    'profit_factor': float,
    'max_drawdown_pct': float,
    'total_trades': int,
    'win_rate': float,
    'sharpe_ratio': float,
    'sortino_ratio': float,
    'expected_payoff': float,
    'recovery_factor': float,
    'forward_result': float,           # From optimization
    'back_result': float,              # From optimization
    'composite_score': float,          # 0-10 Go Live Score
    'is_consistent': bool,             # Forward + Back both positive
    'equity_curve': list[float],       # Full equity curve
    'equity_curve_in_sample': list,    # In-sample portion
    'equity_curve_forward': list,      # Forward portion
    'split_profit_in_sample': float,
    'split_profit_forward': float,
    'report_path': str,                # Path to HTML report
    'charts': {                        # Chart data for dashboard
        'profit_histogram': {...},
        'mfe_mae': [...],
        'holding_times': {...},
    },
    'costs': {
        'total_commission': float,
        'total_swap': float,
    },
}
```

### Step Output

```python
state.steps["9_backtest_robust"] = {
    "passed": bool,
    "result": {
        "best_result": {...},           # Best pass by selection metric
        "results_file": str,            # Path to JSON with all results
        "successful_count": int,
        "total_count": int,
        "gates": {
            "profit_factor": {...},
            "max_drawdown": {...},
            "minimum_trades": {...},
        },
    }
}
```

### Saved Results File

```python
# Saved to: runs/workflow_{id}/backtests_{timestamp}.json
{
    'best_result': {...},
    'all_results': [...],
    'selection': {
        'metric': 'score',
        'best_pass_num': int,
        'best_score': float,
    },
}
```

---

## Data Flow

```
Step 8B Output              Step 9 Process                Step 9 Output
┌─────────────────┐        ┌────────────────────┐        ┌─────────────────┐
│ top_passes[]    │───────▶│ For each pass:     │───────▶│ best_result     │
│ (top 20-30)     │        │   run_backtest()   │        │ all_results[]   │
└─────────────────┘        │   extract_trades() │        │ gates{}         │
                           │   calc_score()     │        └─────────────────┘
                           └────────────────────┘                 │
                                    │                             ▼
                                    ▼                      Step 10 (MC)
                           ┌────────────────────┐
                           │ Select best pass   │
                           │ (by score/profit)  │
                           └────────────────────┘
```

---

## Composite Score Calculation

The "Go Live Score" answers: "Should I trade this live?"

```python
# Code reference: engine/gates.py:319-414

GO_LIVE_SCORE_WEIGHTS = {
    'consistency': 0.25,      # Both back+forward positive
    'total_profit': 0.25,     # Actual money made
    'trade_count': 0.20,      # Statistical confidence
    'profit_factor': 0.15,    # Edge quality
    'max_drawdown': 0.15,     # Risk (inverted)
}

GO_LIVE_SCORE_RANGES = {
    'total_profit': (0, 5000),      # £0-5000 → 0-1
    'trade_count': (50, 200),       # 50-200 trades → 0-1
    'profit_factor': (1.0, 3.0),    # PF 1.0-3.0 → 0-1
    'max_drawdown': (0, 30),        # DD 0-30% → 1-0 (inverted)
    'consistency_min': (0, 2000),   # min(back,fwd) £0-2000 → 0-1
}
```

**Consistency Logic:**
- Both forward+back positive: Full consistency score based on weaker period
- Only one positive: 25% of full score
- Both negative: Zero consistency score

---

## Implementation Notes

### Code References
- `engine/runner.py:1665-1837` — `_step_backtest_passes()` method
- `engine/gates.py:240-261` — `check_all_backtest_gates()`
- `engine/gates.py:319-414` — `calculate_composite_score()`
- `modules/backtest.py:164-457` — `run_backtest()`
- `modules/trade_extractor.py` — Trade extraction and equity curves

### Report Naming Critical

```python
report_name = self._make_report_name('S9_bt', f'pass{pass_num}')
```

**Why deterministic naming matters:**
- MT5 writes into shared folders
- Report collisions cause "wrong run shown" bugs
- Never rely on "most recent file" selection

### Best Pass Selection

```python
# settings.py:192
BEST_PASS_SELECTION = "score"  # Options: "score" or "profit"
```

- **score:** Leaderboard composite score (recommended, balanced)
- **profit:** Raw net profit (higher risk, ignores consistency)

---

*Spec version: 1.0*
*Last updated: 2026-01-11*
