# EA Stress Test System v2 - Build Roadmap

**Status:** Phase 11 Complete (Step 5B EA Fix Loop)
**Last Updated:** 2026-01-01

## Quick Reference

| Setting | Value |
|---------|-------|
| Backtest Period | 4 years (3 in-sample + 1 forward) |
| Data Model | 1-minute OHLC |
| Execution Latency | 10ms |
| Account | £3,000 GBP |
| Platform | MT5 only |
| Interface | Chat with Claude |

---

## Phase 1: Project Setup + Terminal Registry ✓
- [x] Create `settings.py` with thresholds
- [x] Create `terminals.json` for multi-terminal support
- [x] Create `engine/terminals.py` - terminal registry manager
- [x] Test: Can list and select terminals

## Phase 2: Core Modules ✓
- [x] `modules/compiler.py` - compile EA via MT5 terminal
- [x] `modules/backtest.py` - run single backtest (4yr, 1min, 10ms)
- [x] `modules/optimizer.py` - run optimization + parse XML results
- [x] `modules/monte_carlo.py` - shuffle simulation
- [x] `modules/params.py` - extract EA input parameters
- [x] `modules/injector.py` - inject OnTester + safety guards

## Phase 3: Workflow Engine ✓
- [x] `engine/state.py` - JSON state manager
- [x] `engine/runner.py` - 11-step workflow orchestrator
- [x] `engine/gates.py` - pass/fail gate logic

## Phase 4: Dashboard ✓
- [x] `reports/stats_schema.py` - StatsReport dataclass
- [x] `reports/templates/styles.css` - clean CSS
- [x] `reports/templates/dashboard.html` - data-focused view
- [x] `reports/templates/leaderboard.html` - rankings
- [x] `reports/dashboard.py` - generate from StatsReport
- [x] `reports/leaderboard.py` - generate leaderboard

## Phase 5: Skills ✓
- [x] `.claude/skills/stress-test/SKILL.md` - main orchestrator
- [x] `.claude/skills/mql5-lookup/SKILL.md` - reference lookup
- [x] `.claude/skills/mql5-fixer/SKILL.md` - fix compilation errors
- [x] `.claude/skills/param-analyzer/SKILL.md` - param analysis
- [x] `.claude/skills/stats-analyzer/SKILL.md` - LLM analysis spec
- [x] `.claude/skills/ea-improver/SKILL.md` - suggest improvements

## Phase 6: Orchestrator Agent ✓
- [x] `.claude/agents/stress-tester.md` - main orchestrator
- [x] Interactive mode (guides user)
- [x] Autonomous mode (batch runs)

## Phase 7: Reference System ✓
- [x] `reference/mql5.pdf` - 7000-page reference
- [x] `reference/mql5_index.json` - index
- [x] `reference/lookup.py` - search functions
- [x] `reference/cache/` - 48 indexed files

## Phase 8: Analysis System ✓ (NEW)
- [x] `modules/pass_analyzer.py` - filter and analyze optimization passes
- [x] `modules/stats_analyzer.py` - prepare data for Claude
- [x] `reports/workflow_dashboard.py` - generate dashboards from workflow state
- [x] Forward/Back test breakdown in pass analysis
- [x] Consistent pass identification (both periods positive)
- [x] Claude analysis integration in dashboard
- [x] Removed generic placeholder text from dashboard

## Phase 10: Claude Parameter Analysis ✓ (NEW)
- [x] Workflow pauses after Step 3 for Claude analysis
- [x] `/param-analyzer` skill generates WIDE validation params
- [x] `/param-analyzer` skill generates optimization ranges
- [x] Removed Python heuristics (`suggest_param_ranges`, `generate_wide_validation_params`)
- [x] `runner.continue_with_params()` continues workflow with Claude's params
- [x] Automated mode disabled (raises NotImplementedError)
- [x] Updated CLAUDE.md, stress-test skill documentation

## Phase 11: Step 5B EA Fix Loop ✓ (NEW)
- [x] Workflow pauses at Step 5 failure with `status='awaiting_ea_fix'`
- [x] Fix attempt tracking (`fix_attempts`, `max_fix_attempts = 3`)
- [x] `runner.backup_original_ea()` method
- [x] `runner.restart_after_fix()` method
- [x] `/mql5-fixer` skill updated for trade validation diagnosis
- [x] `/stress-test` skill updated with Step 5B flow
- [x] Updated CLAUDE.md with Step 5B documentation

## Phase 12: Post-Step Modules (Optional)
- [ ] `modules/walk_forward.py` - walk-forward validation
- [ ] `modules/multipair.py` - multi-pair testing

---

## Files Created/Modified in Phase 11

```
engine/
├── runner.py             # MODIFIED - Step 5B fix loop, backup_original_ea(), restart_after_fix()

.claude/skills/
├── mql5-fixer/SKILL.md   # MODIFIED - Trade validation diagnosis section
├── stress-test/SKILL.md  # MODIFIED - Step 5B flow documentation

CLAUDE.md                 # MODIFIED - Step 5B documentation
ROADMAP.md                # MODIFIED - Phase 11 added
```

---

## Files Created/Modified in Phase 10

```
engine/
├── runner.py             # MODIFIED - Pauses at Step 3, continue_with_params()

modules/
├── params.py             # MODIFIED - Removed Python heuristics
├── __init__.py           # MODIFIED - Removed heuristic exports

.claude/skills/
├── param-analyzer/SKILL.md   # MODIFIED - Full Claude analysis instructions
├── stress-test/SKILL.md      # MODIFIED - /param-analyzer invocation flow

CLAUDE.md                 # MODIFIED - Step 4 documentation
ROADMAP.md                # MODIFIED - Phase 10 added
```

## Files Created/Modified in Phase 8

```
modules/
├── pass_analyzer.py      # NEW - Analyze optimization passes
├── stats_analyzer.py     # NEW - Format data for Claude
├── backtest.py           # MODIFIED - HTML parsing, forward test config
├── optimizer.py          # MODIFIED - Forward test, XML parsing fix
├── params.py             # MODIFIED - Parameter range validation
├── compiler.py           # MODIFIED - Removed /inc: auto-add

reports/
├── workflow_dashboard.py # NEW - Generate dashboards from workflow
├── templates/
│   ├── dashboard.html    # MODIFIED - Removed generic text, added Claude section
│   └── styles.css        # MODIFIED - Added optimization section styles

settings.py               # MODIFIED - Added DEPOSIT, CURRENCY, FORWARD_MODE
```

---

## Key Fixes Made

### 1. Compiler Include Path
**Problem:** `/inc:MQL5/Include` was being added, causing doubled paths.
**Fix:** Removed automatic `/inc:` - MetaEditor finds includes automatically.

### 2. Backtest Report Location
**Problem:** Looking in wrong directory for reports.
**Fix:** Reports are in terminal `data_path` root, added `Report=` to INI.

### 3. HTML Report Parsing
**Problem:** No parser for MT5 HTML reports.
**Fix:** Added `parse_html_report()` with UTF-16-LE encoding.

### 4. Parameter Range Validation
**Problem:** `SL_ATR_Multiplier` got start=10, stop=5 (invalid).
**Fix:** Reordered pattern matching, added start < stop validation.

### 5. XML Namespace Handling
**Problem:** MT5 XML uses Excel Spreadsheet ML format.
**Fix:** Added `{urn:schemas-microsoft-com:office:spreadsheet}` namespace.

### 6. Forward Test Configuration
**Problem:** No forward test in optimization.
**Fix:** Added `ForwardMode=2`, `ForwardDate` to INI generation.

### 7. Robust Params Failure
**Problem:** Median parameters don't match any actual working pass.
**Fix:** Use best consistent pass instead of synthesized median.

---

## Analysis Pipeline

```
Optimization (8000+ passes)
         ↓
pass_analyzer.py
  - Filter: trades >= 50
  - Filter: PF >= 1.0
  - Extract Forward/Back results
  - Find consistent passes
         ↓
stats_analyzer.py
  - Format for Claude
         ↓
Claude analyzes
  - Verdict (GO/NO-GO)
  - Red flags
  - Parameter recommendations
         ↓
workflow_dashboard.py
  - Include Claude analysis
  - Show all valid passes
  - Highlight consistent ones
```

---

## Testing Status

```bash
pytest tests/ -v  # 183 tests
```

Note: Some tests may need updating after Phase 8 changes.

---

## Next Steps

1. **Test complete workflow** - Run stress test end-to-end with Step 5B fix loop
2. **Walk-forward validation** - Phase 12 module
3. **Multi-pair testing** - Phase 12 module
