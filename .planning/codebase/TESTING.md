# Testing Patterns

**Analysis Date:** 2026-01-11

## Test Framework

**Runner:**
- pytest (standard Python test framework)
- No pytest.ini or pyproject.toml config detected

**Assertion Library:**
- pytest built-in `assert` statements
- Standard comparisons: `==`, `>`, `>=`, `in`

**Run Commands:**
```bash
python -m pytest -q              # Run all tests (quiet mode)
python -m pytest tests/          # Run all tests in tests/
python -m pytest tests/test_monte_carlo.py  # Single file
python -m pytest -v              # Verbose output
```

## Test File Organization

**Location:**
- `tests/` directory (separate from source)
- `tests/conftest.py` for shared fixtures

**Naming:**
- `test_*.py` for test files
- `test_*` for test functions
- `Test*` for test classes

**Structure:**
```
tests/
├── conftest.py           # Shared fixtures
├── test_gates.py         # Gate function tests
├── test_injector.py      # Injector module tests
├── test_integration.py   # Integration tests
├── test_loader.py        # Loader tests
├── test_monte_carlo.py   # Monte Carlo tests
├── test_params.py        # Parameter extraction tests
├── test_reopt_analyzer.py    # Re-optimization tests
├── test_state.py         # State manager tests
├── test_stats_schema.py  # Stats schema tests
├── test_terminals.py     # Terminal registry tests
└── test_trade_extractor.py   # Trade extraction tests
```

## Test Structure

**Suite Organization:**
```python
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from modules.monte_carlo import run_monte_carlo

class TestRunMonteCarlo:
    """Tests for Monte Carlo simulation."""

    def test_basic_simulation(self, sample_trades):
        """Test basic simulation runs successfully."""
        result = run_monte_carlo(sample_trades, iterations=1000)

        assert result['success'] == True
        assert result['iterations'] == 1000
        assert 'ruin_probability' in result
```

**Patterns:**
- Class-based test grouping (`class TestXxx`)
- Fixture injection via parameters
- Descriptive test names (`test_basic_simulation`)
- Docstrings for test purpose

## Fixtures

**Shared Fixtures (conftest.py):**
```python
@pytest.fixture
def temp_dir():
    """Provide a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def sample_trades():
    """Sample trade list for Monte Carlo testing."""
    return [50, 30, -25, 45, -20, ...]

@pytest.fixture
def sample_backtest_results():
    """Sample backtest results for testing."""
    return {'success': True, 'profit': 2500, ...}
```

**Available Fixtures:**
- `temp_dir` - Temporary directory (auto-cleanup)
- `sample_terminals_json` - Mock terminals config
- `sample_ea_code` - Sample MQL5 EA source
- `sample_ea_file` - Sample EA file on disk
- `sample_trades` - Trade list for Monte Carlo
- `sample_backtest_results` - Backtest result dict
- `sample_optimization_results` - Optimization passes

## Mocking

**Framework:**
- pytest fixtures for test data
- No explicit mocking library (unittest.mock not observed)
- File system mocking via temp directories

**Patterns:**
```python
@pytest.fixture
def sample_terminals_json(temp_dir):
    """Create mock terminals.json file."""
    terminals = {"TestBroker": {"path": str(temp_dir / "terminal64.exe"), ...}}
    config_path = temp_dir / "terminals.json"
    config_path.write_text(json.dumps(terminals))
    (temp_dir / "terminal64.exe").touch()  # Create dummy file
    return config_path
```

## Coverage

**Requirements:**
- No coverage target specified
- No coverage configuration detected

**Running Coverage:**
```bash
python -m pytest --cov=. --cov-report=html  # Would work if pytest-cov installed
```

## Test Types

**Unit Tests:**
- Test individual functions in isolation
- Mock external dependencies via fixtures
- Fast execution

**Integration Tests:**
- `test_integration.py` for cross-module tests
- Test workflow steps together
- May require MT5 (skip if not available)

**E2E Tests:**
- Not present (would require full MT5 setup)
- Manual testing via scripts

## Common Patterns

**Assertion Style:**
```python
assert result['success'] == True
assert result['iterations'] == 1000
assert 'ruin_probability' in result
assert 0 <= result['ruin_probability'] <= 100
```

**Testing Dict Returns:**
```python
result = some_function()
assert result['success'] == True
assert 'expected_key' in result
assert result['value'] > threshold
```

**Temporary Files:**
```python
def test_with_temp_file(temp_dir):
    file_path = temp_dir / "test.txt"
    file_path.write_text("content")
    # Test with file...
    # Cleanup automatic via fixture
```

---

*Testing analysis: 2026-01-11*
*Update when test patterns change*
