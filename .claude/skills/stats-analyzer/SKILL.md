# Stats Analyzer Skill

Analyzes stress test results and generates a complete StatsReport for the dashboard.

## Trigger

User says: `/stats-analyzer` or workflow runner calls after optimization/backtest completes

## Inputs

1. **Workflow State JSON** - From `runs/workflow_<EA>_<timestamp>.json`
2. **Backtest Results** - From `modules/backtest.py`
3. **Optimization Results** - From `modules/optimizer.py`
4. **Monte Carlo Results** - From `modules/monte_carlo.py`

## Output

Complete `StatsReport` object (defined in `reports/stats_schema.py`) containing:

- Core metrics (PF, DD, trades, win rate)
- Risk-adjusted metrics (Sharpe, Sortino, Calmar)
- Trade patterns (hourly/daily distribution)
- Market regime analysis
- Parameter stability scores
- Monte Carlo simulation results
- Diagnosis (if gates failed)
- Human-readable insights

---

## Analysis Process

### Step 1: Load Workflow State

```python
from pathlib import Path
import json

state_path = Path(f"runs/workflow_{ea_name}_{timestamp}.json")
state = json.loads(state_path.read_text())
```

### Step 2: Extract Core Metrics

From backtest results:
```python
metrics = Metrics(
    profit=state['backtest']['profit'],
    profit_factor=state['backtest']['profit_factor'],
    max_drawdown_pct=state['backtest']['max_drawdown_pct'],
    total_trades=state['backtest']['total_trades'],
    win_rate=state['backtest']['win_rate'],
    sharpe_ratio=state['backtest']['sharpe_ratio'],
    sortino_ratio=state['backtest']['sortino_ratio'],
    calmar_ratio=state['backtest']['calmar_ratio'],
    recovery_factor=state['backtest']['recovery_factor'],
    expected_payoff=state['backtest']['expected_payoff'],
)
```

### Step 3: Analyze Trade Patterns

From trade history (if available) or estimate from summary:

| Pattern | How to Calculate |
|---------|-----------------|
| Hourly distribution | Count trades per hour (0-23) |
| Daily distribution | Count trades per weekday (Mon-Sun) |
| Holding time | Average position duration |
| Trading style | Classify by holding time |

**Trading Style Classification:**
```python
if avg_holding_minutes < 60:
    style = "scalper"
elif avg_holding_minutes < 240:
    style = "day_trader"
elif avg_holding_minutes < 1440:
    style = "swing"
else:
    style = "position"
```

**Best/Worst Hours:**
```python
best_hour = hourly_distribution.index(max(hourly_distribution))
worst_hour = hourly_distribution.index(min(filter(lambda x: x > 0, hourly_distribution)))
```

### Step 4: Market Regime Analysis

Classify each trade by market condition at entry:

**Regime Detection (requires price data):**
```python
# Using ADX for trend strength
if adx > 25:
    regime = "trending"
elif atr_ratio > 1.5:  # ATR vs average
    regime = "volatile"
else:
    regime = "ranging"
```

**Performance by Regime:**
```python
for regime in ["trending", "ranging", "volatile"]:
    trades_in_regime = filter_by_regime(all_trades, regime)
    calculate:
        - trades: count
        - win_rate: winning / total
        - profit: sum of profits
        - avg_trade: profit / trades
```

**Generate Insight:**
```python
if trending_winrate > ranging_winrate * 1.3:
    insight = f"Performs {int((trending_winrate/ranging_winrate - 1) * 100)}% better in trending markets. Consider filtering ranging periods."
```

### Step 5: Parameter Stability Analysis

Analyze parameter consistency across top passes (DO NOT use median/average values):

```python
# Collect parameter values from top 20 passes
top_passes = optimization_results['results'][:20]
param_values = {}

for pass_data in top_passes:
    for name, value in pass_data.get('params', {}).items():
        if name not in ['Pass', 'Result', 'Forward Result', 'Back Result']:
            param_values.setdefault(name, []).append(value)

# Calculate stability as coefficient of variation (lower = more stable)
param_stability = []
for name, values in param_values.items():
    if len(values) > 1 and all(isinstance(v, (int, float)) for v in values):
        mean = sum(values) / len(values)
        std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        cv = std / abs(mean) if mean != 0 else 1
        stability = max(0, min(1, 1 - cv))  # Higher = more stable

        param_stability.append(ParamStability(
            name=name,
            stable=stability >= 0.7,
            score=stability,
            warning="Fragile - varies significantly across top passes" if stability < 0.5 else ""
        ))

fragile_params = [p.name for p in param_stability if not p.stable]
```

**NOTE**: Never recommend median/average parameter values - these create untested
"Frankenstein" combinations. Always select actual tested passes from optimization.

### Step 6: Process Monte Carlo Results

```python
mc = state['monte_carlo']

monte_carlo = MonteCarlo(
    iterations=mc['iterations'],
    confidence=mc['confidence'],
    ruin_probability=mc['ruin_probability'],
    median_profit=mc['median_profit'],
    worst_case_5pct=mc['worst_case'],
    best_case_95pct=mc['best_case'],
    max_drawdown_median=mc['max_drawdown_median'],
    max_drawdown_worst=mc['max_drawdown_worst'],
)
```

### Step 7: Check Gates & Generate Diagnosis

```python
from engine.gates import (
    check_profit_factor, check_max_drawdown, check_minimum_trades,
    check_monte_carlo_confidence, check_monte_carlo_ruin, diagnose_failure
)

gates = {
    'profit_factor': check_profit_factor(metrics.profit_factor),
    'max_drawdown': check_max_drawdown(metrics.max_drawdown_pct),
    'min_trades': check_minimum_trades(metrics.total_trades),
    'mc_confidence': check_monte_carlo_confidence(monte_carlo.confidence),
    'mc_ruin': check_monte_carlo_ruin(monte_carlo.ruin_probability),
}

all_gates_passed = all(g.passed for g in gates.values())

# Generate diagnosis if failed
if not all_gates_passed:
    failed_gates = [name for name, g in gates.items() if not g.passed]
    diagnosis = Diagnosis(
        failed_gates=failed_gates,
        reasons=diagnose_failure(gates, metrics.__dict__),
        fixes=generate_fixes(failed_gates, metrics, trade_patterns)
    )
```

### Step 8: Generate Insights

**Edge Summary (1-2 sentences):**
```python
edge_parts = []

if metrics.profit_factor >= 2.0:
    edge_parts.append(f"Strong {metrics.profit_factor:.1f} profit factor")
elif metrics.profit_factor >= 1.5:
    edge_parts.append(f"Solid {metrics.profit_factor:.1f} profit factor")

if metrics.win_rate >= 60:
    edge_parts.append(f"high {metrics.win_rate:.0f}% win rate")

if trade_patterns.style == "day_trader" and trade_patterns.best_hour in [13, 14, 15]:
    edge_parts.append("Best performance during London/NY overlap")

if metrics.recovery_factor >= 3:
    edge_parts.append("Recovers quickly from drawdowns")

edge_summary = f"{trade_patterns.style.replace('_', ' ').title()} with {'. '.join(edge_parts)}."
```

**Weaknesses (from analysis):**
```python
weaknesses = []

if market_regime.ranging.win_rate < market_regime.trending.win_rate * 0.7:
    weaknesses.append(
        f"Underperforms in ranging markets ({market_regime.ranging.win_rate:.0f}% win rate "
        f"vs {market_regime.trending.win_rate:.0f}% in trends)"
    )

for param in fragile_params:
    weaknesses.append(f"{param} parameter is fragile - sensitive to small changes")

if metrics.max_drawdown_pct > 20:
    weaknesses.append(f"Drawdown of {metrics.max_drawdown_pct:.1f}% could be reduced")
```

**Recommendations (actionable fixes):**
```python
recommendations = []

# Based on weaknesses
if "ranging" in str(weaknesses).lower():
    recommendations.append("Add ranging market filter to reduce losses during consolidation")

for param in fragile_params:
    if param.lower() in ['stoploss', 'sl', 'stop']:
        recommendations.append("Use ATR-based stops instead of fixed pip values")

if trade_patterns.worst_hour in [0, 1, 2, 3, 4, 5]:  # Asian session
    recommendations.append("Consider reducing position size during Asian session")

if metrics.max_drawdown_pct > 25:
    recommendations.append("Add max daily loss limit to protect against streaks")
```

### Step 9: Build Equity Curve

```python
# From trade history or backtest report
equity_curve = EquityCurve(
    dates=list_of_date_strings,
    values=equity_values,
    in_sample_end_index=find_forward_test_start_index(),
    drawdown_values=calculate_drawdown_at_each_point(),
)
```

### Step 10: Calculate Composite Score

```python
from engine.gates import calculate_composite_score

composite_score = calculate_composite_score({
    'profit_factor': metrics.profit_factor,
    'max_drawdown': metrics.max_drawdown_pct,
    'sharpe_ratio': metrics.sharpe_ratio,
    'sortino_ratio': metrics.sortino_ratio,
    'calmar_ratio': metrics.calmar_ratio,
    'recovery_factor': metrics.recovery_factor,
    'expected_payoff': metrics.expected_payoff,
    'win_rate': metrics.win_rate,
    'param_stability': min(p.score for p in param_stability) if param_stability else 0.5,
})
```

### Step 11: Determine Status

```python
if all_gates_passed and composite_score >= 7:
    status = "ready"
    go_live_ready = True
elif all_gates_passed and composite_score >= 5:
    status = "review"
    go_live_ready = False
elif any(p.score < 0.5 for p in param_stability):
    status = "overfit_risk"
    go_live_ready = False
else:
    status = "failed"
    go_live_ready = False
```

### Step 12: Assemble StatsReport

```python
from reports.stats_schema import StatsReport
from datetime import datetime

report = StatsReport(
    ea_name=state['ea_name'],
    symbol=state['symbol'],
    timeframe=state['timeframe'],
    terminal=state['terminal'],
    workflow_id=state['workflow_id'],

    period_start=state['dates']['start'],
    period_end=state['dates']['end'],
    period_split=state['dates']['forward_start'],

    edge_summary=edge_summary,
    weaknesses=weaknesses,
    recommendations=recommendations,

    metrics=metrics,
    gates=gates,
    all_gates_passed=all_gates_passed,

    trade_patterns=trade_patterns,
    market_regime=market_regime,
    param_stability=param_stability,
    fragile_params=fragile_params,
    streaks=streaks,
    monte_carlo=monte_carlo,
    diagnosis=diagnosis,
    equity_curve=equity_curve,

    composite_score=composite_score,
    go_live_ready=go_live_ready,
    status=status,
    generated_at=datetime.now().isoformat(),
)
```

---

## Output Format

The skill returns a complete StatsReport that can be:
1. Saved as JSON for dashboard rendering
2. Passed to ea-improver for code suggestions
3. Displayed to user as summary

### Example Summary Output

```markdown
## Stats Analysis: TrendFollower_v3

### Verdict: READY FOR GO-LIVE (Score: 8.2/10)

### Edge
Strong 2.1 profit factor day trader. Best performance during London/NY overlap.
Recovers quickly from drawdowns.

### Gates
| Gate | Value | Threshold | Status |
|------|-------|-----------|--------|
| Profit Factor | 2.1 | >= 1.5 | PASS |
| Max Drawdown | 18.5% | <= 30% | PASS |
| Min Trades | 156 | >= 50 | PASS |
| MC Confidence | 85% | >= 70% | PASS |
| MC Ruin | 2.1% | <= 5% | PASS |

### Weaknesses
- Underperforms in ranging markets (45% win rate vs 72% in trends)
- StopLoss parameter is fragile - sensitive to small changes

### Recommendations
1. Add ranging market filter to reduce losses during consolidation
2. Use ATR-based stops instead of fixed pip values
3. Consider reducing position size during Asian session
```

---

## Integration Points

- **Dashboard**: `reports/dashboard.py` consumes StatsReport
- **EA Improver**: `/ea-improver` reads StatsReport for suggestions
- **Leaderboard**: `reports/leaderboard.py` ranks by composite_score
- **Workflow**: `engine/runner.py` calls stats-analyzer at step 11

## Dependencies

- `reports/stats_schema.py` - StatsReport dataclass
- `engine/gates.py` - Gate checking and diagnosis
- `modules/monte_carlo.py` - Risk metrics
- `modules/optimizer.py` - Parameter stability
