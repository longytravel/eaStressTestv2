# Roadmap: EA Stress Test v3 (Clean Redesign)

## Overview

Parallel development of a clean, modular architecture (`ea_stress/`) alongside the existing system (`engine/`, `modules/`, `reports/`). The new system preserves all functionality and skill compatibility while providing clean separation of concerns, dry-run capability, and proper error handling. The old system remains untouched as a fallback.

## Domain Expertise

None (internal Python project, no external domain skills needed)

## Safety Strategy

- **Old code is read-only** — `engine/`, `modules/`, `reports/` never modified
- **New code is additive** — `ea_stress/` created fresh, deletable if needed
- **Skills unchanged** — Continue using old code until Phase 7
- **Validation before swap** — Phase 8 proves equivalence
- **Git safety** — Every phase committed, revertible

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Specification** - Document all APIs, step contracts, skill expectations
- [x] **Phase 2: Core Domain** - Build pure Python domain models (params, metrics, state)
- [x] **Phase 3: MT5 Abstraction** - Build MT5 interface with dry-run capability
- [ ] **Phase 4: Stage Framework** - Create stage interface and implement first stages (1-5) *(In progress)*
- [ ] **Phase 5: Remaining Stages** - Complete stages 6-14
- [ ] **Phase 6: Pipeline & Runner** - Build thin orchestrator
- [ ] **Phase 7: Compatibility Shim** - Legacy API wrapper for skill compatibility
- [ ] **Phase 8: Validation & Migration** - Prove equivalence, swap systems

## Phase Details

### Phase 1: Specification
**Goal**: Document everything the new system must do — APIs, contracts, gates, state transitions
**Depends on**: Nothing (first phase)
**Research**: Unlikely (extracting from existing code)
**Plans**: TBD

The specification captures:
- All 14 step inputs, outputs, and gate conditions
- All skill API contracts (`continue_with_params()`, `run_reopt_analysis()`, etc.)
- State transitions and pause points
- Report formats and outputs

### Phase 2: Core Domain
**Goal**: Build `ea_stress/core/` with pure Python domain models
**Depends on**: Phase 1
**Research**: Unlikely (translating existing patterns)
**Plans**: TBD

Components:
- `params.py` — Parameter models, validation, range generation
- `metrics.py` — Trade metrics, composite scoring, gate calculations
- `state.py` — Workflow state model, transitions, checkpoints

### Phase 3: MT5 Abstraction
**Goal**: Build `ea_stress/mt5/` with interface and dry-run implementation
**Depends on**: Phase 2
**Research**: Unlikely (wrapping existing MT5 operations)
**Plans**: TBD

Components:
- `interface.py` — Abstract MT5 operations (compile, backtest, optimize)
- `terminal.py` — Real MT5 implementation (wraps existing modules)
- `dry_run.py` — Dry-run implementation for testing without MT5

### Phase 4: Stage Framework
**Goal**: Create stage abstraction and implement stages 1-5 (preparation through validation)
**Depends on**: Phase 3
**Research**: Unlikely (extracting from runner.py)
**Plans**: TBD

Components:
- `stages/base.py` — Stage interface (inputs, execute, outputs, validate)
- `stages/s01_load.py` through `stages/s05_validate.py`

### Phase 5: Remaining Stages
**Goal**: Complete stages 6-14 (optimization through multi-pair)
**Depends on**: Phase 4
**Research**: Unlikely (extracting from runner.py)
**Plans**: TBD

Components:
- `stages/s06_create_ini.py` through `stages/s14_multi_pair.py`

### Phase 6: Pipeline & Runner
**Goal**: Build thin orchestrator that sequences stages
**Depends on**: Phase 5
**Research**: Unlikely (new implementation with clean design)
**Plans**: TBD

Components:
- `pipeline/runner.py` — Pipeline execution, stage sequencing
- `pipeline/state_machine.py` — Explicit state transitions, crash recovery

### Phase 7: Compatibility Shim
**Goal**: Legacy API wrapper so skills work unchanged with new internals
**Depends on**: Phase 6
**Research**: Unlikely (API mapping)
**Plans**: TBD

Components:
- `pipeline/legacy.py` — `WorkflowRunner` class with old API, delegates to new system

### Phase 8: Validation & Migration
**Goal**: Prove new system produces identical outputs, swap old for new
**Depends on**: Phase 7
**Research**: Unlikely (testing and comparison)
**Plans**: TBD

Validation:
- Run both systems on same EAs
- Compare outputs (state files, dashboards, metrics)
- Verify skill workflows work unchanged
- Update skills to use new system
- Archive old code (don't delete)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Specification | 5/5 | Complete | 2026-01-11 |
| 2. Core Domain | 1/1 | Complete | 2026-01-11 |
| 3. MT5 Abstraction | 1/1 | Complete | 2026-01-12 |
| 4. Stage Framework | 4/5 | In progress | - |
| 5. Remaining Stages | 0/TBD | Not started | - |
| 6. Pipeline & Runner | 0/TBD | Not started | - |
| 7. Compatibility Shim | 0/TBD | Not started | - |
| 8. Validation & Migration | 0/TBD | Not started | - |
