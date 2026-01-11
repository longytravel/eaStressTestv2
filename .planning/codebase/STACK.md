# Technology Stack

**Analysis Date:** 2026-01-11

## Languages

**Primary:**
- Python 3.x - All application code

**Secondary:**
- MQL5 - Target language for Expert Advisors being tested (read/injected/compiled)

## Runtime

**Environment:**
- Python 3.x (standard CPython)
- Windows required (MetaTrader 5 only runs on Windows)

**Package Manager:**
- pip (no requirements.txt or pyproject.toml detected - dependencies implicit)

**Key Dependencies (inferred from imports):**
- `psutil` - Process management for MT5 terminal control (`modules/optimizer.py`)
- `xml.etree.ElementTree` - Parsing MT5 optimization XML results
- `json` - State persistence and configuration
- `subprocess` - MT5 terminal execution
- `random` - Monte Carlo simulations
- `hashlib` - Deterministic report naming
- `pytest` - Testing framework (`tests/conftest.py`)

## Frameworks

**Core:**
- None (vanilla Python CLI/script-based system)

**Testing:**
- pytest - Unit and integration tests (`tests/`)

**Build/Dev:**
- No build step required (pure Python)

## Key Dependencies

**Critical:**
- MetaTrader 5 terminal - External dependency, drives all backtesting/optimization
- `psutil` - Terminal process management and cleanup

**Infrastructure:**
- Python standard library (pathlib, datetime, json, subprocess, xml, random)

## Configuration

**Environment:**
- `settings.py` - All configuration in single Python module
- `terminals.json` - MT5 terminal registry (paths, data directories)
- No `.env` files or environment variables required

**Key Configuration:**
- Backtest dates (4 years: 3 in-sample + 1 forward)
- Pass/fail thresholds (profit factor, drawdown, min trades)
- Monte Carlo settings (iterations, confidence levels)
- Optimization parameters (timeout, criterion)
- Stress scenario windows and overlays

## Platform Requirements

**Development:**
- Windows only (MetaTrader 5 requirement)
- Python 3.x installation
- MetaTrader 5 terminal(s) installed

**Production:**
- Same as development (local Windows machine with MT5)
- No deployment target (runs locally)

---

*Stack analysis: 2026-01-11*
*Update after major dependency changes*
