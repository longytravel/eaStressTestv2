# EA Improver Skill

Analyzes stress test results and suggests specific MQL5 code improvements.

## Trigger

User says: `/ea-improver` or asks to improve/fix an EA based on test results

## Inputs Required

1. **StatsReport** - From stats-analyzer or workflow state JSON
2. **EA Source Code** - The .mq5 file to improve
3. **Failed Gates** - What needs fixing (from diagnosis)

## Workflow

### Step 1: Load Context

```
Read the workflow state JSON from runs/workflow_<EA>_<timestamp>.json
Extract: diagnosis, weaknesses, recommendations, fragile_params, trade_patterns
Read the EA source file (.mq5)
```

### Step 2: Identify Improvement Areas

Prioritize fixes by impact:

| Issue Type | Priority | Typical Fix |
|------------|----------|-------------|
| Low Profit Factor | HIGH | Improve entries, exits, or R:R |
| High Drawdown | HIGH | Add position sizing, stops |
| Few Trades | MEDIUM | Widen entry conditions |
| Fragile Parameters | MEDIUM | Use ATR-based or adaptive values |
| Poor Regime Performance | LOW | Add market filter |
| Time-based Weakness | LOW | Add session filter |

### Step 3: Generate Suggestions

For each issue, provide:

1. **Problem**: What the stats show
2. **Cause**: Why this is happening (from code analysis)
3. **Solution**: Specific code change
4. **Code**: Exact MQL5 snippet using `/mql5-lookup` for correct syntax

### Step 4: Present to User

Format suggestions as actionable recommendations:

```markdown
## Improvement #1: [Title]

**Problem**: Profit factor 1.2 (below 1.5 threshold)
**Cause**: Average win ($45) barely exceeds average loss ($42)
**Impact**: HIGH - This is a gate failure

### Suggested Fix

Add trailing stop to lock in profits:

```mql5
// Add to OnTick() after position opens
if(PositionSelect(_Symbol))
{
    double currentProfit = PositionGetDouble(POSITION_PROFIT);
    if(currentProfit > TrailingActivation * _Point)
    {
        double newSL = PositionGetDouble(POSITION_PRICE_CURRENT)
                      - TrailingDistance * _Point;
        if(newSL > PositionGetDouble(POSITION_SL))
            trade.PositionModify(_Symbol, newSL,
                                PositionGetDouble(POSITION_TP));
    }
}
```

**Apply this change?** [Yes/No/Modify]
```

## Output Format

```json
{
  "ea_name": "MyEA",
  "total_suggestions": 3,
  "suggestions": [
    {
      "id": 1,
      "title": "Add Trailing Stop",
      "problem": "Low profit factor (1.2)",
      "cause": "Winners not maximized",
      "impact": "HIGH",
      "code_location": "OnTick()",
      "code_before": "// No trailing stop logic",
      "code_after": "// Trailing stop code...",
      "verified_syntax": true
    }
  ],
  "estimated_improvement": "+15-25% profit factor",
  "risks": ["May reduce trade frequency"]
}
```

## Common Improvement Patterns

### Low Profit Factor
- Add trailing stops
- Improve take-profit logic
- Filter low-quality setups
- Use partial closes

### High Drawdown
- Add max daily loss limit
- Reduce position size after losses
- Add equity curve trading
- Tighten stop losses

### Few Trades
- Relax entry filters
- Add multiple entry conditions
- Trade more timeframes/pairs
- Widen spread tolerance

### Fragile Parameters
- Replace fixed values with ATR-based
- Use adaptive periods (e.g., Keltner instead of fixed)
- Add parameter smoothing

### Poor in Ranging Markets
- Add ADX filter (only trade when ADX > 25)
- Add volatility filter
- Detect consolidation patterns

### Poor in Certain Hours
- Add session filter
- Skip low-liquidity hours
- Adjust parameters by session

## MQL5 Lookup Integration

Before suggesting code, ALWAYS verify syntax:

```
Use /mql5-lookup to find:
- Correct function signatures
- Required includes
- Proper error handling
- Platform-specific syntax
```

Example lookups:
- "CTrade PositionModify" - for position modification
- "iATR" - for ATR indicator usage
- "TimeCurrent" - for time-based filters

## Safety Rules

1. **NEVER auto-apply changes** - Always ask user first
2. **Preserve EA logic** - Only enhance, don't restructure
3. **One change at a time** - Let user test incrementally
4. **Explain tradeoffs** - Every fix has downsides
5. **Verify with /mql5-lookup** - No syntax guessing

## Example Session

```
User: /ea-improver

Claude: Loading workflow state for TrendFollower_v3...

Found 3 improvement opportunities:

## Issue #1: Low Profit Factor (1.2)
Your average win ($45) barely exceeds average loss ($42).
I recommend adding a trailing stop to maximize winners.

[Shows code suggestion]

## Issue #2: Fragile StopLoss Parameter
±10% change causes 35% performance drop.
I recommend switching to ATR-based stops.

[Shows code suggestion]

## Issue #3: Poor Ranging Market Performance
45% win rate in ranging vs 72% in trending.
I recommend adding an ADX filter.

[Shows code suggestion]

Which improvement would you like to apply first?
```

## Dependencies

- `/mql5-lookup` - For verified MQL5 syntax
- `/mql5-fixer` - If suggested code doesn't compile
- `reports/stats_schema.py` - StatsReport data contract
