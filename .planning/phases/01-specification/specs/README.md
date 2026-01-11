# Step Specifications

This directory contains detailed specifications for each workflow step.

## Spec Template

Each spec file follows this structure:

```markdown
# Step X: Name

## Overview
[What this step does]

## Inputs
[Exact inputs with types and sources]

## Outputs
[Exact outputs with types and destinations]

## Gate
[Pass/fail conditions with thresholds]

## Implementation Notes
[Current behavior, edge cases, known issues]

## Skill Integration
[If LLM skills interact with this step]
```

## File Naming

- `step-01-load-ea.md` - Step 1: Load EA
- `step-01b-inject-ontester.md` - Step 1B: Inject OnTester
- `step-01c-inject-safety.md` - Step 1C: Inject Safety
- `step-02-compile.md` - Step 2: Compile
- `step-03-extract-params.md` - Step 3: Extract Params

## Source Code References

Specs reference actual code locations using `file:line` notation:
- `engine/runner.py:1443` - Step method in workflow runner
- `engine/gates.py:50` - Gate function
- `modules/injector.py:367` - Injection logic

## Purpose

These specs serve as:
1. **Truth documentation** - What the system actually does (extracted from code)
2. **Contract for redesign** - New `ea_stress/` package must match this behavior
3. **Test criteria** - Validation that new system produces identical outputs
