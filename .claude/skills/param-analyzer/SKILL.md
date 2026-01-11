---
name: param-analyzer
description: Analyze EA parameters to generate wide validation params and optimization ranges. Use when workflow pauses at Step 3, when analyzing Expert Advisor inputs, or when user says /param-analyzer.
---

# Param Analyzer Skill

Claude analyzes EA parameters using intelligence and understanding, not pattern matching.

## TWO-STAGE OPTIMIZATION PHILOSOPHY

**This skill is for the FIRST stage only.** The workflow has two optimization stages:

| Stage | When | Goal | Combination Count |
|-------|------|------|-------------------|
| **1. Initial** | This skill (Step 4) | EXPLORE full parameter space | High is OK - genetic optimizer handles it |
| **2. Refinement** | After Step 8 via `reopt_analyzer` | NARROW based on evidence | Reduced based on actual results |

**CRITICAL:** Do NOT artificially limit parameter coverage in this skill. Include all potentially relevant parameters. The re-optimization phase will refine ranges AFTER we see which values/toggles actually perform well.

---

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
Intelligent start/step/stop ranges for COMPREHENSIVE exploration.
Used in Step 7 optimization. Include ALL relevant parameters - refinement comes later.

---

## CORE PRINCIPLES

### Principle 1: BE AGGRESSIVE - Include More, Not Less

When in doubt, **INCLUDE the parameter** for optimization. The optimizer will reveal what matters. Missing a key parameter is worse than testing one that doesn't matter.

Test ALL feature toggles both ways (true AND false). A disabled feature might be the key to profitability.

### Principle 2: SKIP ONLY WHAT GENUINELY CANNOT AFFECT STRATEGY PERFORMANCE

Read the EA code and UNDERSTAND what each parameter does. Skip ONLY params where optimization makes no logical sense:

- **Identifiers** - Magic numbers, unique IDs (just labels for position tracking)
- **Pure cosmetics** - Colors, line widths, arrow styles, fonts (visual only, zero impact on trades)
- **Debug/development** - Logging flags, print modes, verbose settings
- **String metadata** - Trade comments, order prefixes/suffixes

**DO NOT skip based on name patterns alone.** Read the code. A param called "DisplayMode" might actually affect trade logic. A param called "Style" might control entry style, not visual style.

### Principle 3: UNDERSTAND PARAMETER INTERACTIONS - Avoid Self-Defeating Combinations

This is critical. Read the EA logic and identify params that interact:

**Min/Max pairs:** Ensure ranges do not create impossible conditions
- If optimizing `Min_X` from 20-80 and `Max_X` from 50-100, some combinations (Min=80, Max=50) = zero trades
- Solution: Either constrain ranges to valid combinations, or note the dependency

**Compounding filters:** Multiple tight filters multiply restrictions
- Session filter + Volatility filter + Spread filter + RSI filter = potentially zero trades
- Solution: In wide params, disable or loosen ALL filters. In optimization, be aware that testing all filters at tight settings simultaneously may produce no trades.

**Contradictory toggles:** Some features may conflict
- Example: An EA might have "TradeWithTrend" and "TradeCounterTrend" - enabling both might confuse the logic
- Solution: Read the code to understand if they are mutually exclusive

**Hour wrapping:** Session start/end hours
- Start=22, End=4 might mean overnight trading OR might mean zero hours depending on EA logic
- Solution: Read how the EA handles hour comparison

### Principle 4: SMART STEP SIZING - Meaningful Coverage

**Target: 8-15 values per continuous parameter**

Calculate steps that give meaningful coverage:
- If testing range 10-100, step=10 gives 10 values (good)
- If testing range 10-100, step=1 gives 91 values (too granular for most params)

**Prioritize granularity where it matters most:**
- Core strategy params (entry signals, indicator periods) -> finer steps
- Secondary filters -> coarser steps
- Risk/money management -> moderate steps

**DO NOT artificially limit combinations:**
- The genetic optimizer is DESIGNED to handle large search spaces
- High combination counts are EXPECTED and ACCEPTABLE for the first optimization
- The re-optimization phase (after Step 8) will refine ranges based on actual results
- NEVER reduce parameter coverage to hit an arbitrary combination target

### Principle 5: WIDE PARAMS MUST GUARANTEE TRADES

The wide validation params exist to PROVE the EA can trade. They must:

- **Remove all filters** that could block trades (or set to most permissive values)
- **Extend all time windows** to maximum (trade all hours, all days)
- **Set all thresholds to permissive** (min=0 or tiny, max=huge)
- **Enable features that generate more signals** (if the EA has an "aggressive mode" or similar)

If validation produces zero trades, the optimization is pointless.

### Principle 6: TOGGLE-DEPENDENT PARAMETERS - Never Orphan Dependent Params

**CRITICAL LOGIC RULE:** When a toggle (`Enable_X`, `Use_X`) is being optimized, you MUST also handle its dependent parameters correctly.

**The Pattern:**
```
Enable_Feature = true/false  ← Toggle being optimized
Feature_Param_A = value      ← Only matters when Enable_Feature=true
Feature_Param_B = value      ← Only matters when Enable_Feature=true
```

**The Rule:** If optimizing `Enable_Feature`, you MUST either:
1. **ALSO optimize** `Feature_Param_A` and `Feature_Param_B`, OR
2. **Carefully verify** the fixed values are correct/sensible

**BAD (what NOT to do):**
```python
{'name': 'Enable_Session_Sizing', 'optimize': True},      # Testing on/off
{'name': 'London_Start_Hour', 'optimize': False, 'fixed_value': 7},  # WRONG: Fixed without verification
{'name': 'London_End_Hour', 'optimize': False, 'fixed_value': 16},   # WRONG: May not match server TZ
```

**GOOD (correct approach):**
```python
{'name': 'Enable_Session_Sizing', 'optimize': True},      # Testing on/off
{'name': 'London_Start_Hour', 'start': 9, 'step': 1, 'stop': 11, 'optimize': True},  # Let optimizer find best
{'name': 'London_End_Hour', 'start': 17, 'step': 1, 'stop': 20, 'optimize': True},   # Let optimizer find best
{'name': 'London_Size_Multiplier', 'start': 1.0, 'step': 0.25, 'stop': 2.0, 'optimize': True},
```

**How to identify dependent params:**
1. Read the EA code
2. Find where `Enable_X` is checked: `if(Enable_X) { ... }`
3. Any param used inside that block is a dependent param
4. Mark these relationships when analyzing

### Principle 7: SERVER TIMEZONE AWARENESS - Hour Params Need Context

**Hour-based parameters are MEANINGLESS without timezone context.**

MT5 servers run on different timezones:
- IC Markets: GMT+2 (winter) / GMT+3 (summer DST)
- Pepperstone: GMT+2 / GMT+3
- FTMO: GMT+2 / GMT+3

**Standard session times (in GMT):**
| Session | Open (GMT) | Close (GMT) |
|---------|------------|-------------|
| Sydney | 22:00 | 07:00 |
| Tokyo | 00:00 | 09:00 |
| London | 08:00 | 17:00 |
| New York | 13:00 | 22:00 |

**Converting to server time (example: GMT+2):**
- London 08:00-17:00 GMT = **10:00-19:00 server time**
- New York 13:00-22:00 GMT = **15:00-00:00 server time**

**The Rule for hour params:**
1. **ASK or detect** the server timezone if unknown
2. **Convert** standard session times to server time
3. **Optimize around** the converted times, not arbitrary values

**Example - London session on GMT+2 server:**
```python
# London opens 08:00 GMT = 10:00 server, closes 17:00 GMT = 19:00 server
# Give optimizer flexibility: start 9-11, end 17-20 (server time)
{'name': 'London_Start_Hour', 'start': 9, 'step': 1, 'stop': 11, 'optimize': True},
{'name': 'London_End_Hour', 'start': 17, 'step': 1, 'stop': 20, 'optimize': True},
```

**For general trading hours:**
```python
# If EA has Trading_Start_Hour and Trading_End_Hour
# Don't just use arbitrary 0-23 ranges
# Consider: What hours make sense for this symbol?
# EURUSD: Best during London+NY overlap (15:00-19:00 server on GMT+2)
# USDJPY: Best during Tokyo+London overlap (09:00-11:00 server on GMT+2)
```

---

## PROCESS

### Step 1: Read and Understand the EA

Read the ENTIRE EA source. Understand:
- What is the core strategy logic?
- What does EACH parameter actually control in the code?
- Which parameters are filters that restrict entries?
- Which parameters interact with each other?
- Are there any params that look like filters but are not?

### Step 2: Review Extracted Parameters

Each param has: name, type, base_type, default, comment, optimizable

Map each param to your understanding from the code.

### Step 3: Generate WIDE Validation Params

Create a dict of param values that maximize trade opportunities.

### Step 4: Generate Optimization Ranges

For each parameter, decide:
1. **Skip?** Only if it genuinely cannot affect performance (identifier, visual, debug)
2. **Range?** Based on understanding the param role and sensible bounds
3. **Step?** Target 8-15 values, prioritize granularity on important params
4. **Interactions?** Note any dependencies with other params

### Step 5: Validate Before Output

Before finalizing, check:

- [ ] **No self-defeating ranges:** Min/max pairs cannot create impossible states
- [ ] **All toggles tested both ways:** Every Enable_*/Use_* has optimize=True
- [ ] **Wide params remove filters:** Validation should guarantee trades
- [ ] **Skipped params justified:** Each skip has clear reasoning (not just name-based)
- [ ] **Maximum coverage:** Include all potentially relevant params - genetic optimizer handles large spaces

### Step 6: Output

Call runner.continue_with_params(wide_params, opt_ranges)

---

## EXAMPLES OF INTELLIGENT ANALYSIS

### Example: Session Hours Interaction

**Bad approach:** Testing SessionStart 0-23 step 1 AND SessionEnd 0-23 step 1 = 576 combinations, many invalid

**Good approach:** Constrain ranges so end > start always. E.g., SessionStart 0-12 step 3, SessionEnd 14-22 step 2

### Example: RSI Period - Core vs Secondary

**RSI is core to an RSI Divergence EA:** Fine granularity (step=1, 15 values)
**RSI is just a filter:** Coarse steps (3 values: 7,14,21)

### Example: Identifying a Non-Obvious Skip

A param called Display_Refresh_Bars that only affects ChartRedraw() - skip it.

### Example: A Visual Param That DOES Matter

A param called Arrow_Signal_Bars that actually delays entry by N bars - optimize it!

---

## QUALITY CHECKLIST

Before calling continue_with_params():

1. **Did you read the full EA source?** (Not just param names)
2. **Can you explain what each skipped param does?** (If not, do not skip it)
3. **Are min/max param ranges compatible?** (No impossible combinations)
4. **Are compounding filters accounted for?** (Wide params disable them)
5. **Do step sizes give 8-15 values each?** (Not 1-value, not 100-values)
6. **Are all boolean toggles being tested both ways?**
7. **TOGGLE DEPENDENCIES:** For each `Enable_X` being optimized, are its dependent params ALSO optimized or verified correct?
8. **TIMEZONE:** For hour-based params, have you converted to server time (GMT+2/+3 for most brokers)?
9. **SYMBOL-APPROPRIATE:** Are session/hour ranges sensible for the symbol being tested? (e.g., USDJPY should consider Tokyo session)
10. **MAXIMUM COVERAGE:** Have you included all potentially relevant params? (Do NOT reduce to hit combination targets - reopt handles refinement)
