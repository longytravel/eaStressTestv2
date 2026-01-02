"""
Test Configuration and Fixtures

Provides shared fixtures for all tests.
"""
import pytest
import tempfile
import json
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_dir():
    """Provide a temporary directory that's cleaned up after test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_terminals_json(temp_dir):
    """Create a sample terminals.json file."""
    terminals = {
        "_comment": "Test terminals",
        "TestBroker": {
            "path": str(temp_dir / "terminal64.exe"),
            "data_path": str(temp_dir / "data"),
            "default": True
        },
        "AnotherBroker": {
            "path": str(temp_dir / "other" / "terminal64.exe"),
            "data_path": str(temp_dir / "other" / "data"),
            "default": False
        }
    }

    config_path = temp_dir / "terminals.json"
    config_path.write_text(json.dumps(terminals, indent=2))

    # Create the paths
    (temp_dir / "terminal64.exe").touch()
    (temp_dir / "data").mkdir()
    (temp_dir / "data" / "MQL5" / "Experts").mkdir(parents=True)
    (temp_dir / "data" / "MQL5" / "Include").mkdir(parents=True)
    (temp_dir / "data" / "MQL5" / "Logs").mkdir(parents=True)
    (temp_dir / "data" / "MQL5" / "Files").mkdir(parents=True)

    return config_path


@pytest.fixture
def sample_ea_code():
    """Sample MQL5 EA code for testing."""
    return '''//+------------------------------------------------------------------+
//|                                                     TestEA.mq5 |
//|                        Copyright 2024, Test                     |
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.00"

input int      Period = 14;          // Indicator period
input double   LotSize = 0.1;        // Position size
input int      StopLoss = 50;        // Stop loss in points
input int      TakeProfit = 100;     // Take profit in points
sinput string  Comment = "TestEA";   // Trade comment (not optimizable)
input ENUM_TIMEFRAMES Timeframe = PERIOD_H1;  // Timeframe

int OnInit()
{
    return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
}

void OnTick()
{
    // Trading logic here
}
'''


@pytest.fixture
def sample_ea_file(temp_dir, sample_ea_code):
    """Create a sample EA file for testing."""
    ea_path = temp_dir / "TestEA.mq5"
    ea_path.write_text(sample_ea_code, encoding='utf-8')
    return ea_path


@pytest.fixture
def sample_trades():
    """Sample trade list for Monte Carlo testing."""
    # Mix of wins and losses, realistic distribution
    return [
        50, 30, -25, 45, -20, 60, 35, -30, 55, -15,
        40, -25, 70, 25, -35, 50, 30, -20, 45, -25,
        65, -30, 40, 50, -15, 35, -25, 55, 20, -30,
        75, 35, -20, 40, -25, 50, 30, -35, 60, 25,
        -15, 45, 55, -20, 35, -30, 50, 40, -25, 65,
    ]


@pytest.fixture
def sample_backtest_results():
    """Sample backtest results for testing."""
    return {
        'success': True,
        'profit': 2500,
        'profit_factor': 1.85,
        'max_drawdown_pct': 15.5,
        'total_trades': 120,
        'win_rate': 58.5,
        'sharpe_ratio': 1.6,
        'sortino_ratio': 2.1,
        'calmar_ratio': 2.0,
        'expected_payoff': 20.8,
        'recovery_factor': 2.5,
        'gross_profit': 4500,
        'gross_loss': -2000,
        'max_drawdown': 1550,
    }


@pytest.fixture
def sample_optimization_results():
    """Sample optimization results for testing."""
    return [
        {'result': 2.5, 'profit': 3000, 'profit_factor': 2.2, 'max_drawdown_pct': 12, 'total_trades': 100, 'params': {'Period': 14, 'StopLoss': 50, 'TakeProfit': 100}},
        {'result': 2.3, 'profit': 2800, 'profit_factor': 2.0, 'max_drawdown_pct': 14, 'total_trades': 110, 'params': {'Period': 16, 'StopLoss': 55, 'TakeProfit': 110}},
        {'result': 2.1, 'profit': 2500, 'profit_factor': 1.9, 'max_drawdown_pct': 15, 'total_trades': 95, 'params': {'Period': 14, 'StopLoss': 45, 'TakeProfit': 95}},
        {'result': 2.0, 'profit': 2400, 'profit_factor': 1.85, 'max_drawdown_pct': 16, 'total_trades': 105, 'params': {'Period': 15, 'StopLoss': 50, 'TakeProfit': 100}},
        {'result': 1.9, 'profit': 2200, 'profit_factor': 1.8, 'max_drawdown_pct': 18, 'total_trades': 115, 'params': {'Period': 14, 'StopLoss': 50, 'TakeProfit': 100}},
    ]
