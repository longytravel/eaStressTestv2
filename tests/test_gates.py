"""
Tests for Gate Logic

Tests pass/fail gates and scoring.
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.gates import (
    GateResult,
    check_file_exists,
    check_compilation,
    check_params_found,
    check_minimum_trades,
    check_profit_factor,
    check_max_drawdown,
    check_monte_carlo_confidence,
    check_monte_carlo_ruin,
    check_optimization_passes,
    check_robust_params_found,
    check_all_backtest_gates,
    check_all_monte_carlo_gates,
    check_go_live_ready,
    calculate_composite_score,
    diagnose_failure,
)
import settings


class TestGateResult:
    """Tests for GateResult class."""

    def test_gate_result_pass(self):
        """Test passing gate result."""
        gate = GateResult('test_gate', True, 1.5, 1.0, '>=')

        assert gate.passed == True
        assert 'PASS' in gate.message

    def test_gate_result_fail(self):
        """Test failing gate result."""
        gate = GateResult('test_gate', False, 0.5, 1.0, '>=')

        assert gate.passed == False
        assert 'FAIL' in gate.message

    def test_to_dict(self):
        """Test conversion to dict."""
        gate = GateResult('test_gate', True, 2.0, 1.5, '>=')
        d = gate.to_dict()

        assert d['name'] == 'test_gate'
        assert d['passed'] == True
        assert d['value'] == 2.0
        assert d['threshold'] == 1.5


class TestFileExistsGate:
    """Tests for file exists gate."""

    def test_file_exists(self, sample_ea_file):
        """Test passing when file exists."""
        gate = check_file_exists(str(sample_ea_file))

        assert gate.passed == True

    def test_file_not_exists(self, temp_dir):
        """Test failing when file missing."""
        gate = check_file_exists(str(temp_dir / "nonexistent.mq5"))

        assert gate.passed == False
        assert 'not found' in gate.message


class TestCompilationGate:
    """Tests for compilation gate."""

    def test_compilation_success(self):
        """Test passing compilation."""
        result = {'success': True, 'errors': []}
        gate = check_compilation(result)

        assert gate.passed == True

    def test_compilation_failure(self):
        """Test failing compilation."""
        result = {'success': False, 'errors': ['error 1', 'error 2']}
        gate = check_compilation(result)

        assert gate.passed == False
        assert '2' in gate.message


class TestParamsFoundGate:
    """Tests for params found gate."""

    def test_params_found(self):
        """Test passing with params."""
        params = [
            {'name': 'Period', 'optimizable': True},
            {'name': 'Lots', 'optimizable': True},
        ]
        gate = check_params_found(params)

        assert gate.passed == True
        assert '2 parameters' in gate.message

    def test_no_params(self):
        """Test failing with no params."""
        gate = check_params_found([])

        assert gate.passed == False
        assert '0 parameters' in gate.message

    def test_optimizable_count(self):
        """Test optimizable count in message."""
        params = [
            {'name': 'Period', 'optimizable': True},
            {'name': 'Comment', 'optimizable': False},
        ]
        gate = check_params_found(params)

        assert '1 optimizable' in gate.message


class TestMinimumTradesGate:
    """Tests for minimum trades gate."""

    def test_enough_trades(self):
        """Test passing with enough trades."""
        gate = check_minimum_trades(100)

        assert gate.passed == True
        assert gate.value == 100

    def test_not_enough_trades(self):
        """Test failing with few trades."""
        gate = check_minimum_trades(20)

        assert gate.passed == False
        assert gate.threshold == settings.MIN_TRADES


class TestProfitFactorGate:
    """Tests for profit factor gate."""

    def test_good_pf(self):
        """Test passing with good PF."""
        gate = check_profit_factor(2.0)

        assert gate.passed == True
        assert gate.value == 2.0

    def test_low_pf(self):
        """Test failing with low PF."""
        gate = check_profit_factor(1.2)

        assert gate.passed == False
        assert gate.threshold == settings.MIN_PROFIT_FACTOR


class TestMaxDrawdownGate:
    """Tests for max drawdown gate."""

    def test_low_drawdown(self):
        """Test passing with low drawdown."""
        gate = check_max_drawdown(15.0)

        assert gate.passed == True
        assert gate.operator == '<='

    def test_high_drawdown(self):
        """Test failing with high drawdown."""
        gate = check_max_drawdown(40.0)

        assert gate.passed == False


class TestMonteCarloGates:
    """Tests for Monte Carlo gates."""

    def test_confidence_pass(self):
        """Test passing confidence gate."""
        gate = check_monte_carlo_confidence(80.0)

        assert gate.passed == True

    def test_confidence_fail(self):
        """Test failing confidence gate."""
        gate = check_monte_carlo_confidence(50.0)

        assert gate.passed == False

    def test_ruin_pass(self):
        """Test passing ruin gate."""
        gate = check_monte_carlo_ruin(2.0)

        assert gate.passed == True

    def test_ruin_fail(self):
        """Test failing ruin gate."""
        gate = check_monte_carlo_ruin(10.0)

        assert gate.passed == False


class TestOptimizationGates:
    """Tests for optimization gates."""

    def test_passes_found(self):
        """Test passing with optimization results."""
        gate = check_optimization_passes(100)

        assert gate.passed == True

    def test_no_passes(self):
        """Test failing with no results."""
        gate = check_optimization_passes(0)

        assert gate.passed == False

    def test_robust_params_found(self):
        """Test passing with robust params."""
        params = {'Period': 14, 'StopLoss': 50}
        gate = check_robust_params_found(params)

        assert gate.passed == True

    def test_no_robust_params(self):
        """Test failing with no robust params."""
        gate = check_robust_params_found({})

        assert gate.passed == False


class TestCheckAllBacktestGates:
    """Tests for combined backtest gate checks."""

    def test_all_pass(self, sample_backtest_results):
        """Test all gates passing."""
        result = check_all_backtest_gates(sample_backtest_results)

        assert result['all_passed'] == True
        assert 'profit_factor' in result['gates']
        assert 'max_drawdown' in result['gates']
        assert 'minimum_trades' in result['gates']

    def test_pf_fails(self, sample_backtest_results):
        """Test with failing PF."""
        sample_backtest_results['profit_factor'] = 1.2
        result = check_all_backtest_gates(sample_backtest_results)

        assert result['all_passed'] == False
        assert result['gates']['profit_factor']['passed'] == False


class TestCheckGoLiveReady:
    """Tests for go-live readiness check."""

    def test_ready(self):
        """Test go-live ready."""
        state = {
            'gates': {
                'profit_factor': {'passed': True},
                'max_drawdown': {'passed': True},
                'minimum_trades': {'passed': True},
                'mc_confidence': {'passed': True},
                'mc_ruin': {'passed': True},
            }
        }
        result = check_go_live_ready(state)

        assert result['go_live_ready'] == True
        assert 'READY' in result['message']

    def test_not_ready(self):
        """Test not go-live ready."""
        state = {
            'gates': {
                'profit_factor': {'passed': False},
                'max_drawdown': {'passed': True},
                'minimum_trades': {'passed': True},
                'mc_confidence': {'passed': True},
                'mc_ruin': {'passed': True},
            }
        }
        result = check_go_live_ready(state)

        assert result['go_live_ready'] == False
        assert 'NOT' in result['message']


class TestCompositeScore:
    """Tests for Go Live Score calculation."""

    def test_good_metrics(self):
        """Test Go Live Score with good metrics - consistent, profitable, enough trades."""
        metrics = {
            'profit': 4000,  # Good profit
            'total_trades': 150,  # Good trade count
            'profit_factor': 2.5,  # Good PF
            'max_drawdown_pct': 10.0,  # Low DD
            'forward_result': 1500,  # Positive forward
            'back_result': 1200,  # Positive back = consistent
        }
        score = calculate_composite_score(metrics)

        # Good metrics should result in a decent score (6+)
        assert score >= 6.0
        assert score <= 10.0

    def test_poor_metrics(self):
        """Test Go Live Score with poor metrics."""
        metrics = {
            'profit': 500,  # Low profit
            'total_trades': 40,  # Too few trades
            'profit_factor': 1.2,  # Thin edge
            'max_drawdown_pct': 35.0,  # High DD
            'forward_result': -200,  # Negative forward
            'back_result': 300,  # Only back positive = inconsistent
        }
        score = calculate_composite_score(metrics)

        assert score < 5.0

    def test_empty_metrics(self):
        """Test score with empty metrics."""
        score = calculate_composite_score({})

        # Empty metrics result in low score
        assert score < 2.0

    def test_consistency_matters(self):
        """Test that both forward+back positive scores higher than one positive."""
        # Both positive
        consistent = {
            'profit': 3000,
            'total_trades': 100,
            'profit_factor': 2.0,
            'max_drawdown_pct': 15.0,
            'forward_result': 1000,
            'back_result': 800,
        }

        # Only forward positive
        inconsistent = {
            'profit': 3000,
            'total_trades': 100,
            'profit_factor': 2.0,
            'max_drawdown_pct': 15.0,
            'forward_result': 1000,
            'back_result': -500,
        }

        consistent_score = calculate_composite_score(consistent)
        inconsistent_score = calculate_composite_score(inconsistent)

        # Consistent should score higher
        assert consistent_score > inconsistent_score


class TestDiagnoseFailure:
    """Tests for failure diagnosis."""

    def test_pf_diagnosis(self):
        """Test profit factor diagnosis."""
        gates = {
            'profit_factor': {'passed': False, 'value': 1.2, 'threshold': 1.5, 'operator': '>='}
        }
        metrics = {
            'avg_win': 40,
            'avg_loss': 35,
            'win_rate': 55,
        }
        diagnoses = diagnose_failure(gates, metrics)

        assert len(diagnoses) > 0
        assert 'PF' in diagnoses[0] or 'profit' in diagnoses[0].lower()

    def test_drawdown_diagnosis(self):
        """Test drawdown diagnosis."""
        gates = {
            'max_drawdown': {'passed': False, 'value': 35, 'threshold': 30, 'operator': '<='}
        }
        diagnoses = diagnose_failure(gates, {})

        assert len(diagnoses) > 0
        assert 'Drawdown' in diagnoses[0]

    def test_multiple_failures(self):
        """Test multiple failure diagnoses."""
        gates = {
            'profit_factor': {'passed': False, 'value': 1.2, 'threshold': 1.5, 'operator': '>='},
            'max_drawdown': {'passed': False, 'value': 35, 'threshold': 30, 'operator': '<='},
        }
        diagnoses = diagnose_failure(gates, {'avg_win': 40, 'avg_loss': 35})

        assert len(diagnoses) == 2

    def test_no_failures(self):
        """Test no diagnosis when all pass."""
        gates = {
            'profit_factor': {'passed': True, 'value': 2.0, 'threshold': 1.5},
        }
        diagnoses = diagnose_failure(gates, {})

        assert len(diagnoses) == 0
