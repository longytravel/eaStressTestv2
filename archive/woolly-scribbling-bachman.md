# EA Stress Test System v2 - Clean Rebuild Plan

## Decision Summary
- **Platform**: MT5 only (no MT4 support)
- **Interface**: Chat with Claude (no web UI)
- **Terminals**: Support multiple MT5 terminals (selectable)
- **Feedback Loop**: Suggest improvements only (user approves before code changes)
- **Dashboards**: Fresh design from scratch (clean, visual, interactive)
- **Location**: Completely new folder, lean fresh build

## Backtest Settings (Fixed)
- **Period**: 4 years total (3 in-sample + 1 forward), ending TODAY
- **Data**: 1-minute OHLC
- **Latency**: 10ms execution delay
- **Future**: Tick data support (planned, not v2)

## Deliverables Summary
| Phase | What | Files |
|-------|------|-------|
| 1 | Project setup + terminal registry | 5 |
| 2 | Core modules (compiler, backtest, optimizer, monte carlo, params) | 5 |
| 3 | Workflow engine (state, runner) | 2 |
| 4 | Dashboard + Leaderboard (fresh design, offline HTML) | 5 |
| 5 | Skills (lookup, fixer, param-analyzer, stats-analyzer, ea-improver) | 5 |
| 6 | Orchestrator agent (interactive, guides user) | 1 |
| 7 | Reference system (copy from v1) | ~50 |
| **Total** | **Lean, modular system** | **~73 files** |

## Vision
A lean, interactive system that:
1. **Guides you** through EA testing with an intelligent orchestrator
2. **Runs the 11-step workflow** on MT5 EAs with proper backtesting (4yr, 1min, 10ms)
3. **Analyzes deeply** with a stats expert skill (patterns, edge, weaknesses)
4. **Generates beautiful dashboards** showing insights and metrics
5. **Tracks all runs** in a leaderboard with go-live recommendations
6. **Suggests improvements** using MQL5 reference to fix weaknesses
7. **Supports automation** - can run autonomously when configured

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CHAT WITH CLAUDE                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  /stress-test - Invokes the orchestrator agent            │   │
│  │  Interactive: asks questions, gives options, guides you   │   │
│  │  Autonomous: runs end-to-end when configured              │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Guides the workflow:                                     │   │
│  │  - "Here are your EAs, which shall we test?"             │   │
│  │  - "Which terminal? You have 3 configured."              │   │
│  │  - "Last run of X looked promising, retest?"             │   │
│  │  - Runs 11 steps, pauses at key decisions                │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TERMINAL REGISTRY                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  terminals.json:                                          │   │
│  │  - "Broker1": {path: ..., data_path: ...}                │   │
│  │  - "Broker2": {path: ..., data_path: ...}                │   │
│  │  Active terminal selected per session                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      WORKFLOW ENGINE                            │
│  11 Steps → Dashboard → Leaderboard                             │
│  State tracked in runs/workflow_*.json                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
    ┌────────────────────────┼────────────────────────┐
    ▼                        ▼                        ▼
┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   MODULES    │    │     REPORTS      │    │     SKILLS       │
│              │    │                  │    │                  │
│ - compiler   │    │ - dashboard.py   │    │ - mql5-lookup    │
│ - backtest   │    │ - leaderboard.py │    │ - mql5-fixer     │
│ - optimizer  │    │                  │    │ - param-analyzer │
│ - monte_carlo│    │                  │    │ - stats-analyzer │ ← NEW
│ - walk_fwd   │    │                  │    │ - ea-improver    │
└──────────────┘    └──────────────────┘    └──────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     REFERENCE SYSTEM                            │
│  - MQL5 7000-page PDF (lazy-loaded)                             │
│  - 48 pre-cached common topics                                  │
│  - Searchable index                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## NEW: Stats Analyzer Skill

Expert at finding patterns and insights from trading data:

**What it analyzes:**
- Trade distribution by hour/day/month
- Holding time patterns (scalp vs swing)
- Drawdown recovery characteristics
- Win/loss streak patterns
- Profit per trade distribution
- **Market regime breakdown** - performance in trending vs ranging conditions
- **Parameter stability** - vary each param ±10%, check if results hold
- **Risk-adjusted metrics** - Sharpe, Sortino, Calmar ratios
- **Portfolio correlation** - how this EA correlates with others you've tested
- **Failure diagnosis** - if gates failed, explain WHY and what would fix it

**Output:**
- Clear summary of EA's edge (what works)
- Identified weaknesses (what needs fixing)
- Market regime heatmap (trending vs ranging performance)
- Parameter stability flags (fragile params highlighted)
- Visualizations for dashboard
- Recommendations for ea-improver skill

**Flow:**
```
Optimization → stats-analyzer → Dashboard (insights) → ea-improver (fixes)
```

---

## Directory Structure (Clean)

```
ea-stress-test-v2/
├── CLAUDE.md                    # Quick start + key commands
├── WORKFLOW.md                  # The 11 steps explained
├── settings.py                  # All thresholds (PF, DD, MC, etc.)
├── terminals.json               # MT5 terminal registry
│
├── engine/                      # CORE
│   ├── runner.py               # WorkflowRunner class
│   ├── state.py                # StateManager class
│   ├── terminals.py            # Terminal registry manager
│   └── gates.py                # Pass/fail gate logic
│
├── modules/                     # FUNCTIONAL UNITS (each standalone)
│   ├── compiler.py             # Compile EA
│   ├── injector.py             # Inject OnTester, safety guards
│   ├── params.py               # Extract parameters
│   ├── backtest.py             # Run single backtest
│   ├── optimizer.py            # Run optimization + parse results
│   ├── monte_carlo.py          # Monte Carlo simulation
│   ├── walk_forward.py         # Walk-forward validation (post-step)
│   └── multipair.py            # Multi-pair testing (post-step)
│
├── reports/                     # VISUALIZATION (offline HTML)
│   ├── dashboard.py            # Generate interactive dashboard
│   ├── leaderboard.py          # Generate cross-run leaderboard
│   └── templates/              # HTML/CSS/JS templates
│       ├── dashboard.html
│       ├── leaderboard.html
│       └── styles.css
│
├── .claude/
│   ├── agents/
│   │   └── stress-tester.md    # Main orchestrator agent
│   └── skills/
│       ├── mql5-lookup/        # Reference lookup
│       ├── mql5-fixer/         # Fix compilation errors
│       ├── param-analyzer/     # Intelligent param analysis
│       ├── stats-analyzer/     # Pattern/insight analysis (NEW)
│       └── ea-improver/        # Suggest improvements (NEW)
│
├── reference/                   # MQL5 DOCUMENTATION
│   ├── mql5_index.json
│   ├── indexer.py
│   └── cache/                  # 48 pre-cached topics
│
└── runs/                        # OUTPUT (generated)
    ├── workflow_*.json         # State files
    ├── dashboards/             # Per-run HTML dashboards
    └── leaderboard/            # Aggregated leaderboard
```

---

## Core Workflow (11 Steps)

Keep the proven 11-step structure:

| Step | Name | Module | Gate |
|------|------|--------|------|
| 1 | Load EA | - | File exists |
| 1B | Inject OnTester | `injector.py` | Compiles |
| 1C | Inject Safety | `injector.py` | Compiles |
| 2 | Compile | `compiler.py` | No errors |
| 3 | Extract Params | `params.py` | Params found |
| 4 | Analyze Params | `/param-analyzer` skill | Ranges valid |
| 5 | Validate Trades | `backtest.py` | Trades >= 50 |
| 6 | Create INI | `optimizer.py` | INI valid |
| 7 | Run Optimization | `optimizer.py` | Passes > 0 |
| 8 | Parse Results | `result_parser.py` | Robust params found |
| 9 | Backtest Robust | `backtest.py` | PF >= 1.5, DD <= 30% |
| 10 | Monte Carlo | `monte_carlo.py` | Ruin <= 5%, Conf >= 70% |
| 11 | Generate Reports | `dashboard.py` | Dashboard opens |

---

## NEW: Feedback Loop (ea-improver skill)

After a complete run, the system can:

1. **Analyze Results**
   - Read all metrics from state
   - Identify weaknesses (high DD, low win rate, overfitting, etc.)
   - Compare to leaderboard top performers

2. **Suggest Improvements**
   - Specific, actionable recommendations
   - E.g., "Add trailing stop to reduce drawdown"
   - E.g., "Tighten entry filter - too many losing trades"

3. **Code Changes**
   - Generate enhanced EA version: `EA_v2.mq5`
   - Apply suggested changes using MQL5 reference
   - Document what changed and why

4. **Re-test**
   - Run the enhanced version through the same workflow
   - Compare metrics to baseline
   - Track version history

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Run Test   │────▶│  Analyze     │────▶│  Suggest     │
│   (11 steps) │     │  Weaknesses  │     │  Improvements│
└──────────────┘     └──────────────┘     └──────────────┘
                                                  │
                                                  ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Compare    │◀────│  Re-test     │◀────│  Code        │
│   Versions   │     │  Enhanced EA │     │  Changes     │
└──────────────┘     └──────────────┘     └──────────────┘
```

---

## Orchestrator Agent Behavior

The stress-tester agent guides you through each session:

### Interactive Mode (default)
```
You: /stress-test

Agent: "Welcome! I found 12 EAs in your MT5 Experts folder.

Recent activity:
- TrendFollower_v3 - tested 2 days ago, passed all gates, go-live ready
- ScalperEA - tested last week, failed PF gate (1.2)
- MomentumTrader - never tested

Which would you like to test?
1. TrendFollower_v3 (retest with latest data)
2. ScalperEA (retest after improvements)
3. MomentumTrader (new test)
4. [Enter EA name]"

You: 3

Agent: "You have 2 terminals configured:
1. IC Markets (default)
2. Pepperstone

Which terminal? [1]"

You: 1

Agent: "Starting 11-step workflow for MomentumTrader on IC Markets...

Step 1/11: Loading EA... ✓
Step 2/11: Compiling... ✓
Step 3/11: Extracting parameters...
  Found 8 input parameters. Invoking /param-analyzer...

[param-analyzer runs, shows ranges]

Do these ranges look good? [Y/n]"
```

### Autonomous Mode
```python
# In settings.py
autonomous_mode = True
default_terminal = "IC_Markets"
batch_eas = ["EA1.mq5", "EA2.mq5", "EA3.mq5"]
notify_email = "you@example.com"
```

Agent runs overnight, emails summary when done.

---

## Fresh Build Approach

**Build from scratch, reference v1 only for:**
- MQL5 reference system (7000-page PDF, indexer, cache) - proven, efficient
- Core MT5 terminal command patterns (compile, backtest, optimize CLI args)
- Skill prompt patterns that work (mql5-lookup, mql5-fixer, param-analyzer)

**Build completely new:**
- Dashboard (fresh design, better visuals)
- Leaderboard (clean implementation)
- Workflow engine (simpler, single runner)
- All Python modules (lean, no legacy)
- Stats analyzer skill (deep pattern analysis)
- EA improver skill (uses reference for fixes)

---

## Implementation Order

### Phase 1: Project Setup + Terminal Registry
```
ea-stress-test-v2/
├── CLAUDE.md           # Quick start
├── settings.py         # Thresholds (PF >= 1.5, DD <= 30%, etc.)
├── terminals.json      # Terminal registry
└── engine/terminals.py # Terminal manager
```
```python
# terminals.json
{
  "IC_Markets": {
    "path": "C:/Program Files/IC Markets/terminal64.exe",
    "data_path": "C:/Users/User/AppData/Roaming/MetaQuotes/Terminal/ABC123...",
    "default": true
  },
  "Pepperstone": {
    "path": "...",
    "data_path": "..."
  }
}
```
**Files to create:** 4
**Test:** Can list/select terminals

### Phase 2: Core Modules
```python
# modules/compiler.py
compile_ea(ea_path, terminal) -> {success, exe_path, errors}

# modules/backtest.py
# Always: 4 years (3 in-sample + 1 forward), 1-min OHLC, 10ms latency
run_backtest(ea_path, symbol, timeframe, params, terminal) -> {...}

# modules/optimizer.py
run_optimization(ea_path, ini_path, terminal) -> {passes, xml_path}
parse_results(xml_path) -> [...]

# modules/monte_carlo.py
run_simulation(equity_curve, iterations=10000) -> {confidence, ruin_prob, ...}

# modules/params.py
extract_params(ea_path) -> [{name, type, default, ...}]
```
**Files to create:** 5 modules
**Test:** Each module works standalone with selected terminal

### Phase 3: Workflow Engine
```python
# engine/state.py
class StateManager:
    # Track: terminal used, all step outputs, metrics

# engine/runner.py
class WorkflowRunner:
    # 11 steps with proper gates
    # Always calculates dates dynamically (today - 4 years)
```
**Files to create:** 2
**Test:** Full workflow on test EA

### Phase 4: Dashboard (Fresh Design)
- Interactive equity curves (in-sample | forward split)
- Stats analyzer insights section (patterns, weaknesses)
- Monte Carlo distribution
- Top 20 passes table (click to view)
- Clear pass/fail gates with colors
- Links to: leaderboard, improvements

**Files to create:** 5 (dashboard.py, leaderboard.py, 3 templates)
**Test:** Dashboard is clean, modern, informative

### Phase 5: Skills
```
.claude/skills/
├── mql5-lookup/        # Copy proven patterns from v1
├── mql5-fixer/         # Uses lookup to fix errors
├── param-analyzer/     # Intelligent parameter ranges
├── stats-analyzer/     # NEW: Pattern expert, feeds dashboard + improver
└── ea-improver/        # NEW: Suggests fixes, uses lookup for correct MQL5
```

**stats-analyzer:**
- Trade time distribution (hour/day heatmap)
- Drawdown recovery patterns
- Win/loss streak analysis
- Parameter stability check
- Edge identification

**ea-improver:**
- Reads stats-analyzer output
- Maps weaknesses to fixes
- Uses mql5-lookup for correct code
- Presents changes for user approval

**Files to create:** 5 skill folders
**Test:** Skills chain correctly

### Phase 6: Orchestrator Agent
```markdown
# .claude/agents/stress-tester.md

Interactive orchestrator that:
1. Greets user, shows available EAs
2. Asks which terminal to use
3. Shows previous runs ("X looked promising, retest?")
4. Runs 11 steps with progress updates
5. Pauses at key decisions (param ranges, improvements)
6. Opens dashboard when done
7. Offers: retest, improve, next EA

Autonomous mode:
- Skip prompts, use defaults
- Run batch of EAs overnight
- Email/notify when done
```
**Files to create:** 1 agent definition
**Test:** Interactive flow works, feels engaging

### Phase 7: Reference System
**Copy from v1** - proven, efficient
- mql5_index.json
- indexer.py + lookup.py
- 48 cached topics

**Files to copy:** ~50 reference files

---

## Key Principles

1. **Chat-first** - Everything runs through conversation with Claude
2. **Interactive by default** - Guide user, ask questions, offer choices
3. **Modules are standalone** - Each can be tested/used independently
4. **Skills chain together** - stats-analyzer feeds ea-improver feeds dashboard
5. **Terminal-aware** - Support multiple MT5 installations
6. **Clean separation** - Engine, Modules, Reports, Skills

---

## Dashboard Design (Fresh Build)

The dashboard is the showcase. Build it to impress:

### Single-Run Dashboard
```
┌─────────────────────────────────────────────────────────────────┐
│  EA: MyStrategy_v1   |   EURUSD H1   |   2023-2024             │
│  Score: 8.2/10       |   Go-Live: ✅  Ready                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │             EQUITY CURVE (Interactive)                    │   │
│  │    [In-Sample]          |        [Forward Test]          │   │
│  │    ────────────────────────────────────────────────      │   │
│  │    Hover for trade details, zoom, pan                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │   PROFIT FACTOR  │  │   MAX DRAWDOWN   │  │   WIN RATE   │   │
│  │      2.1         │  │      18.5%       │  │     62%      │   │
│  │   ✅ >= 1.5      │  │   ✅ <= 30%      │  │   Good       │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               MONTE CARLO SIMULATION                      │   │
│  │   Confidence: 85%  |  Ruin Probability: 2.1%             │   │
│  │   [Distribution chart]                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │             OPTIMIZATION PASSES (Top 20)                  │   │
│  │   Click row to see equity curve + details                 │   │
│  │   ─────────────────────────────────────────────────      │   │
│  │   Pass | Profit | PF  | DD%  | Trades | Score            │   │
│  │   042  | $8,240 | 2.1 | 18%  | 156    | 8.2              │   │
│  │   ...                                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  [View Improvements] [Run Stress Test] [Compare Passes]        │
└─────────────────────────────────────────────────────────────────┘
```

### Leaderboard
```
┌─────────────────────────────────────────────────────────────────┐
│  LEADERBOARD - All Tested EAs                                   │
│  Filter: [All] [Go-Live Ready] [Needs Work] [Overfit Risk]     │
├─────────────────────────────────────────────────────────────────┤
│  Rank | EA           | Symbol | Score | PF  | DD% | Status     │
│  ─────────────────────────────────────────────────────────────  │
│   1   | TopEA_v2     | GBPUSD | 9.1   | 2.8 | 12% | ✅ Ready   │
│   2   | MyStrategy   | EURUSD | 8.2   | 2.1 | 18% | ✅ Ready   │
│   3   | TestEA       | USDJPY | 6.5   | 1.6 | 25% | ⚠️ Review  │
│   ...                                                            │
├─────────────────────────────────────────────────────────────────┤
│  [Click row for preview]          [Equity sparkline]            │
└─────────────────────────────────────────────────────────────────┘
```

### Visual Requirements
- Clean, modern design (think TradingView, not MT5 reports)
- Interactive charts (hover, zoom, click)
- Clear pass/fail indicators with color coding
- Mobile-responsive
- Dark mode support

---

## What You Might Be Missing

Based on my understanding of systematic EA testing, here are gaps worth considering:

### 1. **Portfolio Correlation** (RECOMMENDED)
If you're testing multiple EAs, are they correlated? Two profitable EAs that lose money at the same time = double the risk.

**Solution:** Track correlation matrix across EAs in leaderboard. Flag if selecting EAs that move together.

### 2. **Market Regime Awareness**
Does the EA work in trending markets? Ranging? Both? An EA that only works in trends will blow up when markets consolidate.

**Solution:** stats-analyzer could tag trades by regime (volatility, trend strength) and show performance breakdown.

### 3. **Parameter Stability Testing**
You optimize to find "best" params, but are they stable? If slight changes cause big performance drops, the params are curve-fitted.

**Solution:** stats-analyzer runs sensitivity test: vary each param ±10% and check if results hold. Flag fragile parameters.

### 4. **Live vs Backtest Tracking** (FUTURE)
Once you go live, how do you know if the EA is performing as expected? Backtest said X, live says Y.

**Solution:** Export expected metrics, import live results, flag significant divergence.

### 5. **Slippage/Commission Sensitivity**
Your backtest uses 10ms latency, but real execution varies. How sensitive is profit to execution costs?

**Solution:** Run same backtest with 20ms, 50ms, 100ms latency. Show degradation curve.

### 6. **News Event Filter**
Many EAs blow up during high-impact news. Does yours handle it?

**Solution:** ea-improver could check if EA has news filter, suggest adding one if not.

### 7. **Risk-Adjusted Metrics**
You track PF and DD, but also consider:
- **Sharpe Ratio** - return per unit of risk
- **Sortino Ratio** - return per unit of downside risk
- **Calmar Ratio** - return / max drawdown
- **MAR Ratio** - annualized return / max drawdown

**Solution:** Include these in dashboard alongside basic metrics.

### 8. **EA Version Control**
When ea-improver suggests changes, you get EA_v2. Then v3, v4... How do you track what changed between versions?

**Solution:** Store EA snapshots with each run. Show diff between versions in dashboard.

### 9. **Run Archival**
After 100 runs, the runs folder gets messy. Old runs still valuable for comparison.

**Solution:** Archive completed runs to runs/archive/, keep recent N runs active.

### 10. **Failure Analysis**
When an EA fails gates, why? "Failed PF gate" isn't helpful. What would fix it?

**Solution:** stats-analyzer provides specific failure diagnosis: "PF is 1.3 because losing trades average $50 vs winning trades $45. Need better exit or tighter entry filter."

---

## v2 Scope (Confirmed)

**Included in v2:**
1. Portfolio correlation awareness - flag correlated EAs in leaderboard
2. Parameter stability check - stats-analyzer tests ±10% param variations
3. Risk-adjusted metrics - Sharpe, Sortino, Calmar on dashboard
4. Failure diagnosis - explain WHY gates failed and what would fix it
5. Market regime tagging - tag trades as trending/ranging, show breakdown

**Deferred to v2.1+:**
6. Slippage sensitivity testing
7. EA version tracking with diffs
8. Live vs backtest comparison

**Future (v3+):**
9. Tick data support
10. Automated live monitoring
