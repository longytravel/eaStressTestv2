# EA Stress Test Stabilization

## What This Is

A reliability-focused effort to fix bugs and harden the existing EA Stress Test workflow system. The system stress-tests MT5 Expert Advisors through a 14-step gated workflow, but currently suffers from fragility, instruction-following issues, and specific bugs that prevent smooth operation.

## Core Value

Every workflow step must work correctly and reliably before adding anything new. Reliability first.

## Requirements

### Validated

- ✓ 14-step gated workflow engine with pass/fail gates — existing
- ✓ State persistence and recovery between steps — existing
- ✓ LLM integration pause points (Step 3 params, Step 8 pass selection) — existing
- ✓ MT5 terminal orchestration (compile, optimize, backtest) — existing
- ✓ Dashboard and leaderboard HTML generation — existing
- ✓ Monte Carlo simulation for robustness testing — existing
- ✓ Stress scenario testing (rolling windows, tick models) — existing
- ✓ MQL5 documentation lookup for LLM skills — existing

### Active

- [ ] Fix Boolean INI generation (True/False instead of 1/0 for MT5)
- [ ] Fix re-optimization flow (not offered after optimization completes)
- [ ] Add dry-run mode per step (validate inputs/outputs without MT5 execution)
- [ ] Audit and fix reliability issues across all 14 steps
- [ ] Ensure each step follows documented behavior

### Out of Scope

- UI/Dashboard visual changes — separate from core reliability work
- New workflow steps or analysis methods — fix existing before adding
- Major performance optimization — correctness before speed

## Context

The system runs MT5 EAs through a gated workflow designed to be driven by LLMs. Key pain points:

1. **Re-optimization not offered**: After Step 7/8, the workflow should offer to refine parameter ranges and re-run optimization, but this isn't happening.

2. **Boolean INI bug**: MT5 expects numeric booleans (1/0) but the INI generator may be outputting True/False strings.

3. **General fragility**: Steps don't reliably follow documented behavior. Error messages appear unexpectedly. No way to validate individual steps without running full optimization.

4. **Testing gap**: No dry-run capability to test step logic without committing to expensive MT5 operations.

Existing architecture:
- Engine layer: `engine/runner.py`, `engine/state.py`, `engine/gates.py`
- Modules layer: `modules/*.py` (one per step)
- Reports layer: `reports/*.py`
- Reference layer: `reference/*.py` (MQL5 docs)

## Constraints

- **Platform**: Windows only (MT5 requirement)
- **Language**: Python (no rewriting)
- **External dependency**: MetaTrader 5 terminal behavior is fixed

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Reliability before features | System unusable if steps don't work correctly | — Pending |
| Dry-run mode for testing | Enables step validation without full MT5 runs | — Pending |
| Step-by-step audit | Systematic verification of all 14 steps | — Pending |

---
*Last updated: 2026-01-11 after initialization*
