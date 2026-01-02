"""
Tests for Monte Carlo Simulation

Tests Monte Carlo analysis, risk metrics, and gate checks.
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from modules.monte_carlo import (
    run_monte_carlo,
    extract_trades_from_results,
    calculate_risk_metrics,
    check_monte_carlo_gates,
)
import settings


class TestRunMonteCarlo:
    """Tests for Monte Carlo simulation."""

    def test_basic_simulation(self, sample_trades):
        """Test basic simulation runs successfully."""
        result = run_monte_carlo(sample_trades, iterations=1000)

        assert result['success'] == True
        assert result['iterations'] == 1000
        assert 'ruin_probability' in result
        assert 'confidence' in result
        assert 'distribution' in result

    def test_profitable_trades_confidence(self, sample_trades):
        """Test profitable trades have high confidence."""
        # Sample trades are net profitable
        result = run_monte_carlo(sample_trades, iterations=1000)

        # Should have decent confidence
        assert result['confidence'] > 50

    def test_ruin_probability(self, sample_trades):
        """Test ruin probability calculation."""
        result = run_monte_carlo(sample_trades, iterations=1000)

        assert 0 <= result['ruin_probability'] <= 100

    def test_percentiles(self, sample_trades):
        """Test percentile calculations."""
        result = run_monte_carlo(sample_trades, iterations=1000)

        assert 'percentiles' in result
        percentiles = result['percentiles']

        # Should have standard percentiles
        assert 0.05 in percentiles or 0.10 in percentiles
        assert 0.50 in percentiles
        assert 0.95 in percentiles or 0.90 in percentiles

        # Percentiles should be ordered (lower <= median <= higher)
        assert percentiles.get(0.05, percentiles.get(0.10)) <= percentiles[0.50]
        assert percentiles[0.50] <= percentiles.get(0.95, percentiles.get(0.90))

    def test_distribution_output(self, sample_trades):
        """Test distribution list for charting."""
        result = run_monte_carlo(sample_trades, iterations=500)

        assert len(result['distribution']) == 500

    def test_empty_trades(self):
        """Test error with empty trades."""
        result = run_monte_carlo([])

        assert result['success'] == False
        assert 'No trades' in result['errors'][0]

    def test_losing_strategy(self):
        """Test with losing trades - should show poor results."""
        # Heavy losses that exceed ruin threshold
        losing_trades = [-200] * 50  # Total loss $10000 = 100% of initial
        result = run_monte_carlo(losing_trades, iterations=1000)

        assert result['success'] == True
        # Should have high ruin probability (account hits 50% drawdown)
        assert result['ruin_probability'] > 50
        # Low confidence (no profitable scenarios)
        assert result['confidence'] < 10

    def test_winning_strategy(self):
        """Test with all winning trades."""
        winning_trades = [50] * 50  # All wins
        result = run_monte_carlo(winning_trades, iterations=1000)

        assert result['success'] == True
        # Low ruin probability
        assert result['ruin_probability'] < 10
        # High confidence
        assert result['confidence'] > 90

    def test_gate_check_included(self, sample_trades):
        """Test gate check is included in result."""
        result = run_monte_carlo(sample_trades, iterations=1000)

        assert 'passed_gates' in result
        assert 'gate_details' in result
        assert 'ruin_ok' in result['gate_details']
        assert 'confidence_ok' in result['gate_details']

    def test_custom_iterations(self, sample_trades):
        """Test custom iteration count."""
        result = run_monte_carlo(sample_trades, iterations=100)

        assert result['iterations'] == 100
        assert len(result['distribution']) == 100

    def test_custom_ruin_threshold(self, sample_trades):
        """Test custom ruin threshold."""
        # High threshold should result in lower ruin
        result_high = run_monte_carlo(sample_trades, ruin_threshold=0.9, iterations=500)
        # Low threshold should result in higher ruin
        result_low = run_monte_carlo(sample_trades, ruin_threshold=0.3, iterations=500)

        assert result_high['ruin_probability'] <= result_low['ruin_probability']


class TestExtractTradesFromResults:
    """Tests for extracting trades from backtest results."""

    def test_extract_from_trade_list(self):
        """Test extracting from explicit trade list."""
        results = {
            'trades': [
                {'profit': 50},
                {'profit': -25},
                {'profit': 30},
            ]
        }
        trades = extract_trades_from_results(results)

        assert trades == [50, -25, 30]

    def test_estimate_from_summary(self, sample_backtest_results):
        """Test estimating trades from summary stats."""
        trades = extract_trades_from_results(sample_backtest_results)

        # Should generate estimated trades
        assert len(trades) == sample_backtest_results['total_trades']

        # Sum should approximate total profit
        total = sum(trades)
        expected = sample_backtest_results['profit']
        assert abs(total - expected) < abs(expected * 0.1)  # Within 10%

    def test_empty_trades(self):
        """Test with no trades."""
        trades = extract_trades_from_results({'total_trades': 0})
        assert trades == []


class TestCalculateRiskMetrics:
    """Tests for risk-adjusted metric calculations."""

    def test_basic_metrics(self, sample_trades):
        """Test basic risk metrics calculation."""
        result = calculate_risk_metrics(sample_trades)

        assert result['success'] == True
        assert 'sharpe_ratio' in result
        assert 'sortino_ratio' in result
        assert 'calmar_ratio' in result
        assert 'recovery_factor' in result

    def test_positive_returns(self):
        """Test metrics with positive returns."""
        trades = [50, 30, 40, 60, 35]  # All positive
        result = calculate_risk_metrics(trades)

        assert result['success'] == True
        assert result['sharpe_ratio'] > 0
        assert result['total_return_pct'] > 0

    def test_max_drawdown(self, sample_trades):
        """Test max drawdown calculation."""
        result = calculate_risk_metrics(sample_trades)

        assert 'max_drawdown_pct' in result
        assert result['max_drawdown_pct'] >= 0
        assert result['max_drawdown_pct'] <= 100

    def test_volatility(self, sample_trades):
        """Test volatility calculation."""
        result = calculate_risk_metrics(sample_trades)

        assert 'volatility_pct' in result
        assert 'downside_volatility_pct' in result
        assert result['volatility_pct'] >= 0

    def test_empty_trades_error(self):
        """Test error with empty trades."""
        result = calculate_risk_metrics([])

        assert result['success'] == False


class TestCheckMonteCarloGates:
    """Tests for Monte Carlo gate checking."""

    def test_passing_gates(self):
        """Test gates that should pass."""
        mc_results = {
            'ruin_probability': 2.0,  # < 5%
            'confidence': 80.0,  # > 70%
        }
        gates = check_monte_carlo_gates(mc_results)

        assert gates['passed'] == True
        assert gates['ruin_probability']['passed'] == True
        assert gates['confidence']['passed'] == True

    def test_failing_ruin_gate(self):
        """Test failing ruin probability gate."""
        mc_results = {
            'ruin_probability': 10.0,  # > 5%
            'confidence': 80.0,
        }
        gates = check_monte_carlo_gates(mc_results)

        assert gates['passed'] == False
        assert gates['ruin_probability']['passed'] == False
        assert gates['confidence']['passed'] == True

    def test_failing_confidence_gate(self):
        """Test failing confidence gate."""
        mc_results = {
            'ruin_probability': 2.0,
            'confidence': 50.0,  # < 70%
        }
        gates = check_monte_carlo_gates(mc_results)

        assert gates['passed'] == False
        assert gates['confidence']['passed'] == False

    def test_gate_messages(self):
        """Test gate messages are included."""
        mc_results = {
            'ruin_probability': 2.0,
            'confidence': 80.0,
        }
        gates = check_monte_carlo_gates(mc_results)

        assert 'message' in gates['ruin_probability']
        assert 'message' in gates['confidence']
        assert 'PASS' in gates['ruin_probability']['message']


class TestIntegration:
    """Integration tests for Monte Carlo workflow."""

    def test_full_workflow(self, sample_backtest_results):
        """Test complete Monte Carlo workflow."""
        # 1. Extract trades from backtest
        trades = extract_trades_from_results(sample_backtest_results)
        assert len(trades) > 0

        # 2. Run simulation
        mc_result = run_monte_carlo(trades, iterations=500)
        assert mc_result['success'] == True

        # 3. Calculate risk metrics
        risk_metrics = calculate_risk_metrics(trades)
        assert risk_metrics['success'] == True

        # 4. Check gates
        gates = check_monte_carlo_gates(mc_result)
        assert 'passed' in gates
