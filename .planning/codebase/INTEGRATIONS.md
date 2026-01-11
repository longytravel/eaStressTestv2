# External Integrations

**Analysis Date:** 2026-01-11

## APIs & External Services

**MetaTrader 5 Terminal:**
- Core integration - All backtesting, optimization, and trade simulation
  - Execution: `subprocess.run()` with command-line arguments
  - Configuration: INI files generated per-run
  - Results: XML files parsed from terminal output directories
  - Locations: Configured in `terminals.json`

## Data Storage

**Databases:**
- None (file-based architecture)

**File Storage:**
- `runs/` - Workflow state JSON files, optimization results
- `runs/dashboards/` - Generated HTML dashboards per workflow
- `runs/leaderboard/` - Cross-workflow leaderboard HTML
- `reference/cache/` - MQL5 reference PDF index cache

**Caching:**
- File-based caching for MQL5 reference lookups (`reference/cache/`)

## Authentication & Identity

**Auth Provider:**
- None (local tool, no authentication)

## Monitoring & Observability

**Error Tracking:**
- None (errors stored in workflow state JSON)

**Analytics:**
- None

**Logs:**
- Console output (print statements)
- Workflow state includes `errors` array for step failures

## CI/CD & Deployment

**Hosting:**
- Local execution only (Windows desktop)

**CI Pipeline:**
- None detected
- `python -m pytest -q` for local testing

## Environment Configuration

**Development:**
- Required: `terminals.json` with MT5 terminal paths
- No environment variables
- All config in `settings.py`

**Staging:**
- Not applicable (local tool)

**Production:**
- Same as development

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## MetaTrader 5 Integration Details

**Terminal Registry:**
- `terminals.json` - Maps broker names to terminal paths
- Fields: `path` (terminal64.exe), `data_path` (AppData location), `default`
- Example: `"IC_Markets": {"path": "C:/Users/User/Projects/terminal64.exe", ...}`

**Communication Protocol:**
1. Generate INI configuration file
2. Launch terminal via `subprocess` with `/config` flag
3. Wait for terminal to complete (with timeout)
4. Parse XML results from `data_path/MQL5/Reports/`
5. Kill any stuck terminal/metatester processes via `psutil`

**Report Files:**
- Deterministic naming: `{workflow_id}_{tag}_{extra}` to avoid collisions
- Stored in: `{data_path}/MQL5/Reports/`

**EA Injection:**
- System modifies source .mq5 files to inject:
  - OnTester() function for custom optimization criterion
  - Safety parameters (max spread, max slippage)
- Compilation via terminal's built-in compiler

---

*Integration audit: 2026-01-11*
*Update when adding/removing external services*
