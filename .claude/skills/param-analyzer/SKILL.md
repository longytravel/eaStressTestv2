# Param Analyzer Skill

Generates intelligent parameter configurations for EA stress testing using Claude's intelligence.

## Trigger

- Workflow pauses at Step 3 with status `awaiting_param_analysis`
- User says `/param-analyzer`
- Automatically invoked by `/stress-test` skill after parameter extraction

## Purpose

Claude analyzes EA parameters and generates TWO outputs:

### Output 1: WIDE Validation Params
Single values that MAXIMIZE trading opportunities to PROVE the EA can trade.
Used in Step 5 validation backtest. Goal: 50+ trades.

### Output 2: Optimization Ranges
Intelligent start/step/stop ranges for finding optimal settings.
Used in Step 7 optimization.

---

## INSTRUCTIONS FOR CLAUDE

When this skill is invoked, Claude MUST:

### Step 1: Read the EA Source Code

```python
# Read the EA to understand what each parameter does
ea_path = runner.ea_path  # or from workflow state
```

Understand:
- What is this EA's strategy?
- What does each parameter control?
- Which parameters are filters that restrict trading?
- Which parameters should NEVER be optimized?

### Step 2: Read the Extracted Parameters

```python
params = runner.params  # List of extracted parameters
```

Each param has: name, type, base_type, default, comment, optimizable

### Step 3: Generate WIDE Validation Params

**Goal:** Create parameter values that MAXIMIZE trading opportunities.

**Strategy by parameter type:**

| Parameter Type | Wide Value Strategy |
|---------------|---------------------|
| Session hours (start/end) | 0-23 (trade all day) |
| ATR/volatility min | 0 or 1 (no minimum) |
| ATR/volatility max | 10000 (no maximum) |
| Spread max | 1000 (allow any spread) |
| Min zone/size | 1 (smallest possible) |
| Max zone/size | 10000 (largest possible) |
| Lookback/period | Shorter = more signals |
| Entry thresholds | Most permissive values |
| Max touches/age | Very high (keep zones valid) |
| Max concurrent trades | High (5-10) |
| Multipliers for entry | Low (easier to trigger) |
| Safety guards | Disable or permissive |

**NEVER include in wide params:**
- MagicNumber
- DebugMode
- Risk/lot size (keep default for validation)

### Step 4: Generate Optimization Ranges

**Goal:** Create intelligent ranges that find optimal settings without over-fitting.

**Categorize each parameter:**

| Category | Indicators | Range Strategy |
|----------|-----------|----------------|
| risk | sl, stoploss, risk, buffer | 50-200% of default, step=10-20 |
| reward | tp, takeprofit, target, multiple | 50-300% of default |
| period | period, length, bars, lookback | 50-200% of default |
| threshold | level, min, max, tolerance | ±50% of default |
| timing | hour, session, day | Full valid range |
| multiplier | mult, factor, ratio | 0.5x-2x of default |
| filter | atr, spread, overlap | Test on/off or range |

**NEVER optimize:**
- MagicNumber, ID, identifier
- DebugMode, logging, display
- Safety guard params (EAStressSafety_*)

**Format for each optimizable param:**
```json
{
  "name": "ParamName",
  "start": 10,
  "step": 5,
  "stop": 50,
  "optimize": true,
  "category": "period",
  "rationale": "Lookback period: 10-50 with step 5 (9 values)"
}
```

### Step 5: Output the Results

Claude must provide code that continues the workflow:

```python
wide_params = {
    # Claude's intelligent wide values here
}

opt_ranges = [
    # Claude's intelligent optimization ranges here
]

result = runner.continue_with_params(wide_params, opt_ranges)
```

---

## Example Analysis

**For an EA with session filter, ATR filter, and stop loss:**

**WIDE Validation Params:**
```python
wide_params = {
    # Session - trade all day
    "SessionStartHour": 0,
    "SessionEndHour": 23,

    # ATR - accept all volatility
    "MinATRPips": 0,
    "MaxATRPips": 10000,

    # Spread - accept any
    "MaxSpreadPips": 1000,

    # Keep risk at default for validation
    # (don't include StopLoss, RiskPercent)
}
```

**Optimization Ranges:**
```python
opt_ranges = [
    {"name": "SessionStartHour", "start": 0, "step": 2, "stop": 12, "optimize": True,
     "category": "timing", "rationale": "Session start: test 0-12 hours"},

    {"name": "SessionEndHour", "start": 12, "step": 2, "stop": 23, "optimize": True,
     "category": "timing", "rationale": "Session end: test 12-23 hours"},

    {"name": "StopLoss", "start": 25, "step": 10, "stop": 100, "optimize": True,
     "category": "risk", "rationale": "SL: 25-100 points, step 10"},

    {"name": "MinATRPips", "start": 10, "step": 10, "stop": 50, "optimize": True,
     "category": "filter", "rationale": "Min ATR filter: 10-50"},

    {"name": "MagicNumber", "optimize": False,
     "category": "identifier", "rationale": "Position ID - never optimize"},
]
```

---

## Workflow Integration

The stress-test skill should:

1. Run `runner.run()` which pauses after Step 3
2. Invoke `/param-analyzer` skill
3. Claude reads EA code and params
4. Claude generates wide_params and opt_ranges
5. Call `runner.continue_with_params(wide_params, opt_ranges)`
6. Workflow continues with Steps 4-11

---

## Quality Checks

Before outputting, Claude should verify:

- [ ] All restrictive filters are widened in wide_params
- [ ] Session hours extended to 0-23
- [ ] ATR/spread limits removed or very permissive
- [ ] MagicNumber NOT in wide_params or optimization
- [ ] Safety params NOT optimized
- [ ] Optimization ranges are reasonable (not millions of combinations)
- [ ] Each opt range has a rationale
