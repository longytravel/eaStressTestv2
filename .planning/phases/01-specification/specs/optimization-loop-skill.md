# /optimization-loop Skill Specification

## Purpose

Handle the **entire optimization loop** with intelligence:
- Maintain context across multiple optimization passes
- Make decisions about when to refine and when to proceed
- Select final passes for backtesting

**Replaces:** Separate Steps 6, 7, 8, 8B and the `/stats-analyzer` skill

## Invocation

**Trigger:** Called after Step 5 validation passes

```
User: /stress-test (or workflow running)
→ Steps 1-5 complete
→ Step 5 validates EA trades
→ /optimization-loop invoked automatically
```

**Inputs received:**
- `initial_optimization_ranges`: ALL parameters with wide exploration ranges
- `ea_path`: Path to compiled .ex5 file
- `symbol`, `timeframe`: Trading pair and period
- `settings`: All optimization-related settings

## Skill Contract

### Entry Conditions
- [ ] Compiled EA exists (Step 2 passed)
- [ ] Parameters extracted (Step 3 passed)
- [ ] EA validated to trade (Step 5 passed)
- [ ] `initial_optimization_ranges` provided (Step 4 output)

### Exit Conditions
- [ ] `selected_passes` populated with pass indices
- [ ] All selected passes have complete parameter values
- [ ] Optimization history saved to workflow state
- [ ] Analysis reports available for dashboard

### State Machine

```
                    ┌─────────────┐
                    │   START     │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
             ┌──────│ OPTIMIZING  │──────┐
             │      └──────┬──────┘      │
             │             │             │
             │     (MT5 running)         │
             │             │             │
             │             ▼             │
             │      ┌─────────────┐      │
             │      │  ANALYZING  │      │
             │      └──────┬──────┘      │
             │             │             │
             │    (Python stats)         │
             │             │             │
             │             ▼             │
             │      ┌─────────────┐      │
             │      │  DECIDING   │◄─────┘
             │      └──────┬──────┘
             │             │
             │    ┌────────┴────────┐
             │    │                 │
             │    ▼                 ▼
             │  LOOP?            PROCEED?
             │    │                 │
             │    ▼                 ▼
             └─►REFINE        ┌─────────────┐
                              │  SELECTING  │
                              └──────┬──────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │    DONE     │
                              └─────────────┘
```

## Internal Loop

### Pass N Execution (Delegates to Python)

```python
# 1. Generate INI
ini_path = create_ini_file(
    ea_name=compiled_ea.name,
    symbol=symbol,
    timeframe=timeframe,
    param_ranges=current_ranges,  # refined on pass 2+
    report_name=f"{ea_name}_S7_opt_{symbol}_{timeframe}",
)

# 2. Run optimization
result = run_optimization(
    ea_path=compiled_ea,
    symbol=symbol,
    timeframe=timeframe,
    param_ranges=current_ranges,
    timeout=settings.OPTIMIZATION_TIMEOUT,
    on_progress=log_progress,
)

# 3. Parse results
passes = parse_optimization_results(result['xml_path'])

# 4. Analyze parameters
analysis = analyze_for_reoptimization(
    all_passes=filtered_passes,
    top_passes=top_20_passes,
    original_ranges=current_ranges,
)
```

### Decision Point (LLM)

After receiving the analysis, the LLM decides:

**LOOP** = Refine ranges and run again
**PROCEED** = Select passes and continue to Step 9

#### Decision Factors

| Factor | LOOP Signal | PROCEED Signal |
|--------|-------------|----------------|
| Pass number | Pass 1 (exploration) | Pass 2+ (refined) |
| Toggle patterns | Strong patterns found | No clear patterns |
| Clustering | Parameters cluster tightly | Good diversity |
| Quality | Few valid passes | Many quality passes |
| Iteration count | < MAX_ITERATIONS | = MAX_ITERATIONS |

#### Decision Criteria

```python
# After Pass 1
if pass_number == 1:
    if analysis.recommendation.should_reoptimize:
        decision = "LOOP"  # Refine based on patterns
    else:
        decision = "LOOP"  # Always do at least 2 passes
    reason = "Pass 1 was exploration - refining for focused search"

# After Pass 2
elif pass_number == 2:
    if reopt_count >= settings.REOPT_MAX_ITERATIONS:
        decision = "PROCEED"  # Hard limit reached
        reason = "Max re-optimizations (2) reached"
    elif analysis.recommendation.should_reoptimize:
        decision = "PAUSE"  # Discuss with user
        reason = "Patterns found - would another pass help?"
    else:
        decision = "PROCEED"
        reason = "Good diversity, no strong patterns"

# After Pass 3+
else:
    decision = "PROCEED"
    reason = "Diminishing returns - sufficient iterations"
```

## Range Refinement (LLM + Python)

When LOOP is decided, refine ranges:

### 1. Fix Toggle Winners

From `toggle_analysis`:
```python
for name, toggle in analysis.toggle_analysis.items():
    if toggle.recommendation == 'FIX_TRUE':
        # Remove from optimization, fix to True
        new_ranges = [r for r in current_ranges if r['name'] != name]
        new_ranges.append({'name': name, 'fixed': True})
    elif toggle.recommendation == 'FIX_FALSE':
        new_ranges = [r for r in current_ranges if r['name'] != name]
        new_ranges.append({'name': name, 'fixed': False})
```

### 2. Remove Dead Parameters

When toggle is fixed to FALSE, dependent params are dead:
```python
# Example: Use_RSI_Filter = False
dead_params = ['RSI_Period', 'RSI_Overbought', 'RSI_Oversold']
new_ranges = [r for r in new_ranges if r['name'] not in dead_params]
```

The LLM identifies these dependencies from parameter naming patterns:
- `Use_X` → removes `X_*` params
- `Enable_X` → removes `X_*` params
- `Avoid_X` → may affect `X_*` params

### 3. Narrow Clustered Ranges

From `continuous_analysis`:
```python
for name, cont in analysis.continuous_analysis.items():
    if cont.recommendation == 'NARROW_RANGE':
        refined = cont.suggested_refined_range
        for r in new_ranges:
            if r['name'] == name:
                r['start'] = refined['start']
                r['stop'] = refined['stop']
                r['step'] = refined['step']
```

### 4. Handle Interactions

Some parameters only matter together:
```python
# If RSI and MACD both used, their interaction matters
# If RSI disabled, MACD interaction with RSI is irrelevant
```

The LLM uses trading logic to identify these patterns.

## Pass Selection (LLM)

When PROCEED is decided, select passes for backtesting:

### Selection Criteria

1. **Primary:** Go Live Score (composite)
2. **Diversity:** Don't select 20 passes with identical params
3. **Consistency:** Prefer both back+forward positive
4. **Risk profiles:** Include some aggressive, some conservative

### Selection Logic

```python
# Start with top 30 by score
candidates = sorted(all_passes, key=lambda p: p['composite_score'], reverse=True)[:30]

# Ensure diversity (no identical param sets)
selected = []
seen_params = set()

for p in candidates:
    param_hash = hash(frozenset(p['params'].items()))
    if param_hash not in seen_params:
        selected.append(p)
        seen_params.add(param_hash)
    if len(selected) >= 20:
        break

# Prioritize consistent passes (both back+forward positive)
consistent = [p for p in selected if p['forward_result'] > 0 and p['back_result'] > 0]
```

### Output Format

```python
selected_passes = [
    {
        'pass_index': 1,
        'params': {'StopLoss': 50, 'TakeProfit': 100, ...},
        'composite_score': 8.5,
        'profit': 2500,
        'forward_result': 1200,
        'back_result': 1300,
    },
    ...
]
```

## Pause Point: After Pass 2

**When:** After Pass 2, if patterns still found and MAX_ITERATIONS not reached

**Purpose:** Discuss with user whether another pass would help

**Presentation:**

```
════════════════════════════════════════════════════════════════
OPTIMIZATION CHECKPOINT: Pass 2 Complete
════════════════════════════════════════════════════════════════

Results:
- Total passes: 5000
- Valid passes: 1234
- Top 20 analyzed

Patterns Found:
• Use_RSI_Filter: False wins (85% in top passes)
• TakeProfit clusters at 150 (CV=0.15)

Recommendation: Re-optimization could improve focus

Options:
1. LOOP - Run Pass 3 with refined ranges:
   - Fix Use_RSI_Filter=False
   - Narrow TakeProfit to 120-180

2. PROCEED - Continue with current top passes
   - Good diversity already
   - May be diminishing returns

Current iteration: 2 of 2 maximum

What would you like to do?
════════════════════════════════════════════════════════════════
```

**User responses:**
- "loop" / "refine" → Execute Pass 3 with refined ranges
- "proceed" / "continue" → Select passes and move to Step 9
- Custom refinement → Apply user's specific changes

## /stats-analyzer Deprecation

The `/stats-analyzer` skill is **deprecated**. Its functionality is absorbed:

| /stats-analyzer | → /optimization-loop |
|-----------------|----------------------|
| Load workflow state | Maintained internally |
| Analyze passes | Part of decision loop |
| Select top N | Done with full context |
| Generate insights | Integrated with analysis |
| Reopt recommendations | Core decision point |

**Benefits of consolidation:**
- Full optimization context available
- No context-switching between skills
- Reopt analysis integrated with selection
- Single responsibility for optimization quality

## Error Handling

### Optimization Fails (0 passes)

```python
if result['passes'] == 0:
    diagnose:
        - Check if EA trades at all (Step 5 should catch this)
        - Check if ranges are too tight
        - Check if symbol has data
    offer:
        - Widen ranges
        - Try different symbol
        - Review EA logic
```

### Timeout

```python
if 'timeout' in result['errors']:
    suggest:
        - Reduce parameter count
        - Widen steps (fewer combinations)
        - Use simpler model (OHLC vs tick)
```

### No Valid Passes (all filtered)

```python
if valid_passes == 0:
    check_thresholds:
        - MIN_TRADES too high for this symbol?
        - Profit filter too strict?
    offer:
        - Lower MIN_TRADES temporarily
        - Review EA performance expectations
```

## Integration with Workflow

### Before (Step 5)

```python
# Step 5 provides:
validated = True  # EA confirmed trading
validation_trades = 150  # Trade count achieved
initial_ranges = [...]  # ALL params with wide ranges
```

### After (Step 9)

```python
# /optimization-loop provides:
selected_passes = [...]  # 20-30 passes to backtest
optimization_history = [...]  # All passes from all runs
analysis_reports = {...}  # Parameter importance data

# Step 9 then:
for pass_data in selected_passes:
    equity_curve = backtest(pass_data['params'])
    monte_carlo = run_mc(equity_curve)
```

### Dashboard Integration

The optimization loop provides data for:
- Pass table (top 20 with metrics)
- Parameter importance heatmap
- Optimization history timeline
- Refinement decision log
