# Phase 1: Specification - Context

**Gathered:** 2026-01-11
**Status:** Ready for planning

<vision>
## How This Should Work

A hybrid extraction approach: read the existing codebase to understand what each step actually does today, then document it as a clean contract while flagging where current behavior diverges from ideal.

The output is 14 separate spec files — one per workflow step. Each spec is a self-contained document that completely describes that step's contract, so the new implementation can be built from the spec without constantly referencing old code.

This isn't about capturing bugs as "features" — it's about understanding current reality well enough to design something better.

</vision>

<essential>
## What Must Be Nailed

- **Gate contracts** — Crystal clear pass/fail conditions for each step
- **Data flow** — Exact inputs and outputs with formats
- **Skill integration points** — Where LLM skills hook in, what they receive, what they must return

All three are equally important. The specs must be complete enough that Phase 2+ can build from them without guesswork.

</essential>

<boundaries>
## What's Out of Scope

- No firm boundaries set — open to recommendations as work progresses
- The focus is extraction and documentation, not implementation decisions
- Fixing bugs or adding features happens in later phases

</boundaries>

<specifics>
## Specific Ideas

No specific format requirements — use whatever structure communicates most clearly. The step table in CLAUDE.md is a good reference point for the level of detail expected.

</specifics>

<notes>
## Additional Context

User is testing the GSD workflow and trusts judgment calls. Recommendations welcome throughout the process.

</notes>

---

*Phase: 01-specification*
*Context gathered: 2026-01-11*
