# Step 10: Monte Carlo Simulation

**Status:** Automatic step
**Gate:** MC confidence and ruin probability
**Input:** Trade list from best pass (Step 9)

---

## Overview

Step 10 runs Monte Carlo simulation on the **best pass** from Step 9. The simulation:
- Shuffles trade order to test sequence dependency
- Estimates probability of ruin (50% drawdown)
- Calculates confidence intervals for expected profit
- Produces distribution data for dashboard charts

**Why Monte Carlo?** A profitable backtest might have been "lucky" with trade sequence. Monte Carlo reveals whether the edge is robust across all possible trade orderings.

---

## Inputs

### From Step 9 (Backtest Top Passes)

```python
backtest_results: dict  # Best pass result
# Contains:
{
    'pass_num': int,
    'profit': float,
    'profit_factor': float,
    'total_trades': int,
    'gross_profit': float,
    'gross_loss': float,
    'win_rate': float,
    # ... plus equity_curve, trades, etc.
}
```

### Configuration

```python
# Code reference: settings.py:84-87

MC_ITERATIONS = 10000       # Number of simulation iterations
MC_CONFIDENCE_MIN = 70.0    # Minimum confidence percentage (gate)
MC_RUIN_MAX = 5.0           # Maximum ruin probability percentage (gate)
```

---

## Process

### 1. Extract Trades

```python
# Code reference: engine/runner.py:1839-1843

trades = extract_trades_from_results(self.backtest_results)
pass_num = self.backtest_results.get('pass_num')

if not trades:
    return False, {'error': 'No trades to simulate'}
```

### Trade Extraction Options

```python
# Code reference: modules/monte_carlo.py:163-196

def extract_trades_from_results(backtest_results: dict) -> list[float]:
    # If we have actual trade list
    if 'trades' in backtest_results:
        return [t.get('profit', 0) for t in backtest_results['trades']]

    # Estimate from summary statistics
    total_trades = backtest_results.get('total_trades', 0)
    win_rate = backtest_results.get('win_rate', 50) / 100
    gross_profit = backtest_results.get('gross_profit', 0)
    gross_loss = backtest_results.get('gross_loss', 0)

    winning_trades = int(total_trades * win_rate)
    losing_trades = total_trades - winning_trades

    avg_win = gross_profit / winning_trades if winning_trades > 0 else 0
    avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0

    trades = []
    trades.extend([avg_win] * winning_trades)
    trades.extend([avg_loss] * losing_trades)  # Already negative

    return trades
```

### 2. Run Monte Carlo Simulation

```python
# Code reference: engine/runner.py:1848

self.mc_results = run_monte_carlo(trades)
```

### Monte Carlo Algorithm

```python
# Code reference: modules/monte_carlo.py:16-160

def run_monte_carlo(
    trades: list[float],
    initial_balance: float = 10000,
    iterations: int = None,           # Default: MC_ITERATIONS (10000)
    ruin_threshold: float = 0.5,      # 50% drawdown = ruin
    confidence_levels: list[float] = None,  # [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
) -> dict:
```

**Simulation Loop:**

```python
for _ in range(iterations):
    # Shuffle trade order
    shuffled = trades.copy()
    random.shuffle(shuffled)

    # Simulate equity curve
    balance = initial_balance
    peak = initial_balance
    max_dd = 0
    ruined = False

    for trade in shuffled:
        balance += trade
        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
        if dd >= ruin_threshold:  # 50% drawdown
            ruined = True

    final_profits.append(balance - initial_balance)
    max_drawdowns.append(max_dd * 100)

    if ruined:
        ruin_count += 1
```

### 3. Calculate Statistics

```python
# Sort for percentile calculations
final_profits.sort()
max_drawdowns.sort()

# Core metrics
ruin_probability = (ruin_count / iterations) * 100
profitable_count = sum(1 for p in final_profits if p > 0)
confidence = (profitable_count / iterations) * 100

expected_profit = sum(final_profits) / n
median_profit = final_profits[n // 2]

worst_case = percentiles[0.05]    # 5th percentile
best_case = percentiles[0.95]    # 95th percentile

dd_median = max_drawdowns[n // 2]
dd_worst = max_drawdowns[int(0.95 * n)]
```

### 4. Check Gates

```python
# Code reference: engine/runner.py:1854-1856

gate_results = gates.check_all_monte_carlo_gates(self.mc_results)
for name, gate_data in gate_results['gates'].items():
    self.state.update_gates({name: gate_data})
```

---

## Gates

### Gate Functions

```python
# Code reference: engine/gates.py:187-209

def check_monte_carlo_confidence(confidence: float) -> GateResult:
    """Gate 10a: Check Monte Carlo confidence level."""
    passed = confidence >= settings.MC_CONFIDENCE_MIN  # Default: 70%
    return GateResult(
        name='mc_confidence',
        passed=passed,
        value=round(confidence, 2),
        threshold=settings.MC_CONFIDENCE_MIN,
        operator='>=',
        message=f"{'PASS' if passed else 'FAIL'}: MC Confidence {confidence}% (minimum: {settings.MC_CONFIDENCE_MIN}%)"
    )

def check_monte_carlo_ruin(ruin_prob: float) -> GateResult:
    """Gate 10b: Check Monte Carlo ruin probability."""
    passed = ruin_prob <= settings.MC_RUIN_MAX  # Default: 5%
    return GateResult(
        name='mc_ruin',
        passed=passed,
        value=round(ruin_prob, 2),
        threshold=settings.MC_RUIN_MAX,
        operator='<=',
        message=f"{'PASS' if passed else 'FAIL'}: Ruin probability {ruin_prob}% (maximum: {settings.MC_RUIN_MAX}%)"
    )
```

### Combined Gate Check

```python
# Code reference: engine/gates.py:264-283

def check_all_monte_carlo_gates(mc_results: dict) -> dict:
    confidence = mc_results.get('confidence', 0)
    ruin = mc_results.get('ruin_probability', 100)

    gates = {
        'mc_confidence': check_monte_carlo_confidence(confidence),
        'mc_ruin': check_monte_carlo_ruin(ruin),
    }

    all_passed = all(g.passed for g in gates.values())
    return {'all_passed': all_passed, 'gates': {...}}
```

---

## Settings Reference

```python
# Code reference: settings.py:84-87

MC_ITERATIONS = 10000        # Number of simulation iterations
MC_CONFIDENCE_MIN = 70.0     # Minimum confidence percentage
MC_RUIN_MAX = 5.0            # Maximum ruin probability percentage
```

**Gate Thresholds Explained:**
- **MC_CONFIDENCE_MIN (70%):** At least 70% of shuffled sequences must end profitable
- **MC_RUIN_MAX (5%):** At most 5% of sequences can hit 50% drawdown (ruin)

---

## Outputs

### Monte Carlo Results

```python
# Code reference: modules/monte_carlo.py:137-160

{
    'success': True,
    'iterations': 10000,
    'ruin_probability': float,        # 0-100%, gate: <= 5%
    'confidence': float,              # 0-100%, gate: >= 70%
    'expected_profit': float,         # Mean of all sequences
    'median_profit': float,           # 50th percentile
    'worst_case': float,              # 5th percentile
    'best_case': float,               # 95th percentile
    'max_drawdown_median': float,     # Median max drawdown %
    'max_drawdown_worst': float,      # 95th percentile drawdown %
    'percentiles': {
        0.05: float,
        0.10: float,
        0.25: float,
        0.50: float,
        0.75: float,
        0.90: float,
        0.95: float,
    },
    'drawdown_percentiles': {
        # Same percentiles for max drawdown distribution
    },
    'distribution': list[float],      # All final profits (for histogram)
    'drawdown_distribution': list,    # All max drawdowns (for histogram)
    'passed_gates': bool,
    'gate_details': {
        'ruin_ok': bool,
        'ruin_threshold': 5.0,
        'confidence_ok': bool,
        'confidence_threshold': 70.0,
    },
    'errors': [],
}
```

### Step Output

```python
# Code reference: engine/runner.py:1864-1868

state.steps["10_monte_carlo"] = {
    "passed": bool,
    "result": {
        # All mc_results fields above...
        'pass_num': int,               # Which pass was simulated
        'gates': {
            'mc_confidence': {...},
            'mc_ruin': {...},
        },
    }
}
```

### State Metrics Update

```python
# Code reference: engine/runner.py:1859-1862

self.state.update_metrics({
    'mc_confidence': self.mc_results.get('confidence', 0),
    'mc_ruin_probability': self.mc_results.get('ruin_probability', 100),
})
```

---

## Data Flow

```
Step 9 Output              Step 10 Process               Step 10 Output
┌─────────────────┐       ┌───────────────────────┐      ┌─────────────────┐
│ best_result     │──────▶│ extract_trades()      │──────▶│ confidence: N%  │
│ (best pass)     │       │ run_monte_carlo()     │      │ ruin_prob: N%   │
└─────────────────┘       │   shuffle 10000x      │      │ percentiles{}   │
                          │   track ruin/profit   │      │ distributions[] │
                          └───────────────────────┘      └─────────────────┘
                                     │                            │
                                     ▼                            ▼
                          ┌───────────────────────┐        Step 11 (Reports)
                          │ check_gates()         │
                          │ confidence >= 70%?    │
                          │ ruin <= 5%?           │
                          └───────────────────────┘
```

---

## Interpretation Guide

### What the Metrics Mean

| Metric | Good Value | Bad Value | Interpretation |
|--------|------------|-----------|----------------|
| confidence | ≥70% | <70% | % of sequences ending profitable |
| ruin_probability | ≤5% | >5% | % hitting 50% drawdown |
| median_profit | > $0 | < $0 | Typical outcome |
| worst_case (5%) | > -50% | < -50% | 95 in 100 do better than this |

### Why Gates Fail

**Confidence < 70%:**
- Too much depends on trade sequence
- Edge is thin or overfitted
- Solution: Improve entry signals, reduce position sizes

**Ruin > 5%:**
- High risk of account blowup
- Large position sizes or correlated losses
- Solution: Reduce position sizing, add circuit breakers

---

## Dashboard Display

Monte Carlo results appear in the dashboard for each pass:

```javascript
// Dashboard data structure
passes[pass_num].monte_carlo = {
    'confidence': 72.5,
    'ruin_probability': 3.2,
    'median_profit': 2847.50,
    'worst_5pct': -1250.00,
    'best_95pct': 8920.00,
}
```

**Note:** Monte Carlo is only computed for the **best pass** (workflow-level). Other passes show empty Monte Carlo data unless individually simulated.

---

## Implementation Notes

### Code References
- `engine/runner.py:1839-1868` — `_step_monte_carlo()` method
- `modules/monte_carlo.py:16-160` — `run_monte_carlo()` function
- `modules/monte_carlo.py:163-196` — `extract_trades_from_results()`
- `engine/gates.py:264-283` — `check_all_monte_carlo_gates()`
- `engine/gates.py:187-209` — Individual gate checks

### Trade Estimation Fallback

If actual trade list unavailable, trades are estimated from summary stats:
- Winning trades = total_trades × win_rate
- Losing trades = total_trades × (1 - win_rate)
- Each winning trade = gross_profit / winning_trades
- Each losing trade = gross_loss / losing_trades

This is less accurate than actual per-trade data but allows Monte Carlo even for optimization-only passes.

### Ruin Definition

**Ruin = 50% drawdown from peak equity**

This threshold represents account-destroying losses that most traders cannot recover from psychologically or financially.

---

*Spec version: 1.0*
*Last updated: 2026-01-11*
