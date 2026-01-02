"""
Tests for Stats Schema

Tests dataclass definitions and serialization.
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from reports.stats_schema import (
    Metrics,
    Gate,
    TradePatterns,
    RegimePerformance,
    MarketRegime,
    ParamStability,
    Streaks,
    MonteCarlo,
    Diagnosis,
    EquityCurve,
    StatsReport,
    create_sample_report,
)


class TestMetrics:
    """Tests for Metrics dataclass."""

    def test_default_values(self):
        """Test default values."""
        metrics = Metrics()

        assert metrics.profit == 0
        assert metrics.profit_factor == 0
        assert metrics.total_trades == 0

    def test_custom_values(self):
        """Test custom values."""
        metrics = Metrics(
            profit=5000,
            profit_factor=2.5,
            total_trades=100,
            win_rate=65,
        )

        assert metrics.profit == 5000
        assert metrics.profit_factor == 2.5
        assert metrics.win_rate == 65


class TestGate:
    """Tests for Gate dataclass."""

    def test_create_gate(self):
        """Test creating gate."""
        gate = Gate(
            name='profit_factor',
            passed=True,
            value=2.0,
            threshold=1.5,
            operator='>=',
        )

        assert gate.name == 'profit_factor'
        assert gate.passed == True
        assert gate.value == 2.0


class TestTradePatterns:
    """Tests for TradePatterns dataclass."""

    def test_default_distributions(self):
        """Test default distribution arrays."""
        patterns = TradePatterns()

        assert len(patterns.hourly_distribution) == 24
        assert len(patterns.daily_distribution) == 7

    def test_custom_patterns(self):
        """Test custom patterns."""
        patterns = TradePatterns(
            style='scalper',
            holding_time_avg_minutes=15,
            best_hour=9,
        )

        assert patterns.style == 'scalper'
        assert patterns.holding_time_avg_minutes == 15
        assert patterns.best_hour == 9


class TestMarketRegime:
    """Tests for MarketRegime dataclass."""

    def test_default_regime(self):
        """Test default market regime."""
        regime = MarketRegime()

        assert regime.dominant_regime == 'unknown'
        assert isinstance(regime.trending, RegimePerformance)
        assert isinstance(regime.ranging, RegimePerformance)

    def test_regime_with_data(self):
        """Test regime with performance data."""
        regime = MarketRegime(
            trending=RegimePerformance(trades=50, win_rate=70, profit=3000, avg_trade=60),
            ranging=RegimePerformance(trades=30, win_rate=45, profit=500, avg_trade=16.7),
            dominant_regime='trending',
            insight='Performs better in trends',
        )

        assert regime.trending.trades == 50
        assert regime.ranging.win_rate == 45
        assert regime.dominant_regime == 'trending'


class TestParamStability:
    """Tests for ParamStability dataclass."""

    def test_stable_param(self):
        """Test stable parameter."""
        param = ParamStability(
            name='Period',
            stable=True,
            score=0.92,
        )

        assert param.stable == True
        assert param.score == 0.92

    def test_fragile_param(self):
        """Test fragile parameter."""
        param = ParamStability(
            name='StopLoss',
            stable=False,
            score=0.35,
            warning='Sensitive to changes',
        )

        assert param.stable == False
        assert param.warning == 'Sensitive to changes'


class TestMonteCarlo:
    """Tests for MonteCarlo dataclass."""

    def test_default_values(self):
        """Test default Monte Carlo values."""
        mc = MonteCarlo()

        assert mc.iterations == 10000
        assert mc.confidence == 0
        assert mc.ruin_probability == 100

    def test_passing_mc(self):
        """Test passing Monte Carlo."""
        mc = MonteCarlo(
            iterations=10000,
            confidence=85,
            ruin_probability=2.5,
            median_profit=7500,
        )

        assert mc.confidence == 85
        assert mc.ruin_probability == 2.5


class TestDiagnosis:
    """Tests for Diagnosis dataclass."""

    def test_no_failures(self):
        """Test diagnosis with no failures."""
        diag = Diagnosis()

        assert diag.failed_gates == []
        assert diag.reasons == []
        assert diag.fixes == []

    def test_with_failures(self):
        """Test diagnosis with failures."""
        diag = Diagnosis(
            failed_gates=['profit_factor', 'max_drawdown'],
            reasons=['PF too low', 'DD too high'],
            fixes=['Improve entry', 'Add trailing stop'],
        )

        assert len(diag.failed_gates) == 2
        assert len(diag.fixes) == 2


class TestEquityCurve:
    """Tests for EquityCurve dataclass."""

    def test_empty_curve(self):
        """Test empty equity curve."""
        curve = EquityCurve()

        assert curve.dates == []
        assert curve.values == []

    def test_with_data(self):
        """Test curve with data."""
        curve = EquityCurve(
            dates=['2024-01', '2024-02', '2024-03'],
            values=[10000, 10500, 11000],
            in_sample_end_index=2,
        )

        assert len(curve.dates) == 3
        assert curve.values[-1] == 11000
        assert curve.in_sample_end_index == 2


class TestStatsReport:
    """Tests for StatsReport dataclass."""

    def test_default_report(self):
        """Test default report values."""
        report = StatsReport()

        assert report.ea_name == ''
        assert report.go_live_ready == False
        assert report.composite_score == 0

    def test_report_to_dict(self):
        """Test report serialization."""
        report = StatsReport(
            ea_name='TestEA',
            symbol='EURUSD',
            composite_score=8.5,
        )

        d = report.to_dict()

        assert d['ea_name'] == 'TestEA'
        assert d['symbol'] == 'EURUSD'
        assert d['composite_score'] == 8.5

    def test_nested_to_dict(self):
        """Test nested objects in serialization."""
        report = StatsReport(
            metrics=Metrics(profit=5000, profit_factor=2.0),
            monte_carlo=MonteCarlo(confidence=80),
        )

        d = report.to_dict()

        assert d['metrics']['profit'] == 5000
        assert d['monte_carlo']['confidence'] == 80


class TestSampleReport:
    """Tests for sample report creation."""

    def test_sample_report_valid(self):
        """Test sample report has valid data."""
        report = create_sample_report()

        assert report.ea_name == 'TrendFollower_v3'
        assert report.symbol == 'EURUSD'
        assert report.go_live_ready == True
        assert report.composite_score == 8.2

    def test_sample_report_metrics(self):
        """Test sample report metrics."""
        report = create_sample_report()

        assert report.metrics.profit > 0
        assert report.metrics.profit_factor > 1.5
        assert report.metrics.total_trades >= 50

    def test_sample_report_gates(self):
        """Test sample report gates."""
        report = create_sample_report()

        assert len(report.gates) > 0
        assert report.all_gates_passed == True

    def test_sample_report_insights(self):
        """Test sample report insights."""
        report = create_sample_report()

        assert report.edge_summary != ''
        assert len(report.weaknesses) > 0
        assert len(report.recommendations) > 0

    def test_sample_report_serializable(self):
        """Test sample report can be JSON serialized."""
        import json

        report = create_sample_report()
        d = report.to_dict()

        # Should not raise
        json_str = json.dumps(d, default=str)
        assert len(json_str) > 0

        # Should be parseable
        parsed = json.loads(json_str)
        assert parsed['ea_name'] == 'TrendFollower_v3'
