# Codebase Concerns

**Analysis Date:** 2026-01-11

## Tech Debt

**Large runner.py file:**
- Issue: `engine/runner.py` is 104KB with WorkflowRunner class spanning 2000+ lines
- Files: `engine/runner.py`
- Why: All 14 steps implemented in single class
- Impact: Hard to navigate, test, and maintain
- Fix approach: Extract step implementations to separate modules, keep runner as thin orchestrator

**No requirements.txt or pyproject.toml:**
- Issue: Dependencies not declared (psutil, pytest inferred from code)
- Files: Project root
- Why: Started as quick script, grew organically
- Impact: New environment setup requires trial-and-error
- Fix approach: Add `pyproject.toml` with dependencies

**sys.path manipulation everywhere:**
- Issue: Every module has `sys.path.insert(0, ...)` for imports
- Files: All `modules/*.py`, `tests/*.py`, `engine/*.py`
- Why: Avoid package structure setup
- Impact: Fragile imports, IDE confusion
- Fix approach: Proper package structure with `setup.py` or `pyproject.toml`

## Known Bugs

**No known bugs documented in code.**

## Security Considerations

**Hardcoded terminal paths in terminals.json:**
- Risk: Terminal paths contain username, could leak in logs/reports
- Files: `terminals.json`
- Current mitigation: File is gitignored (likely)
- Recommendations: Use environment variables or relative paths

**No input validation on EA paths:**
- Risk: Could potentially read/execute unintended files
- Files: `engine/runner.py`
- Current mitigation: User provides paths directly
- Recommendations: Validate paths are within expected directories

## Performance Bottlenecks

**MT5 terminal startup time:**
- Problem: Each step that runs MT5 has significant startup overhead
- Files: `modules/optimizer.py`, `modules/backtest.py`
- Measurement: 5-10 seconds per terminal launch
- Cause: MT5 terminal is heavyweight external process
- Improvement path: Batch operations where possible, reuse terminal sessions

**Large workflow state files:**
- Problem: State JSON can grow large with full optimization results
- Files: `runs/workflow_*.json`
- Measurement: Potentially 10MB+ with full pass data
- Cause: All results stored in single JSON
- Improvement path: Already partially addressed with `_save_results()` for large data

## Fragile Areas

**MT5 report parsing:**
- Files: `modules/optimizer.py`, `modules/backtest.py`
- Why fragile: Depends on MT5 output format which may vary by version
- Common failures: XML parsing errors, missing fields
- Safe modification: Add defensive parsing with fallbacks
- Test coverage: Limited

**Report file collisions:**
- Files: `engine/runner.py` (`_make_report_name()`)
- Why fragile: MT5 writes to shared folders, overlapping runs can collide
- Common failures: Wrong results shown in dashboard
- Safe modification: Already addressed with deterministic naming
- Test coverage: Not tested

## Scaling Limits

**Single terminal execution:**
- Current capacity: One workflow at a time per terminal
- Limit: MT5 terminal locks during optimization
- Symptoms at limit: Stuck processes, timeout errors
- Scaling path: Multi-terminal support (different brokers)

**Genetic optimization timeout:**
- Current capacity: 10 hours (`OPTIMIZATION_TIMEOUT = 36000`)
- Limit: Complex EAs with many parameters may exceed
- Symptoms at limit: Incomplete optimization, process killed
- Scaling path: Distributed optimization (not currently supported)

## Dependencies at Risk

**MetaTrader 5 terminal:**
- Risk: External dependency, version changes may break integration
- Impact: Core functionality depends on MT5 CLI interface
- Migration plan: No alternative (MT5 is the target platform)

**psutil (process management):**
- Risk: Used for terminal cleanup, but import is conditional
- Files: `modules/optimizer.py`
- Impact: Stuck processes if psutil not available
- Migration plan: Make psutil required dependency

## Missing Critical Features

**No formal dependency management:**
- Problem: No requirements.txt or pyproject.toml
- Current workaround: Users install packages manually as errors appear
- Blocks: Clean environment setup, CI/CD
- Implementation complexity: Low

**No CI/CD pipeline:**
- Problem: Tests only run manually
- Current workaround: `python -m pytest -q` before commits
- Blocks: Automated regression testing
- Implementation complexity: Medium

## Test Coverage Gaps

**MT5 integration tests:**
- What's not tested: Actual MT5 terminal execution
- Files: `modules/optimizer.py`, `modules/backtest.py`
- Risk: Integration issues with real MT5 go undetected
- Priority: Medium (requires MT5 setup)
- Difficulty to test: Requires MT5 installation, broker account

**End-to-end workflow:**
- What's not tested: Full workflow from Step 1 to Step 14
- Risk: Step interactions may break
- Priority: High
- Difficulty to test: Long runtime, MT5 dependency

**Report generation:**
- What's not tested: Dashboard HTML generation
- Files: `reports/workflow_dashboard.py`, `reports/leaderboard.py`
- Risk: Broken dashboards in production
- Priority: Medium
- Difficulty to test: Output validation of HTML

---

*Concerns audit: 2026-01-11*
*Update as issues are fixed or new ones discovered*
