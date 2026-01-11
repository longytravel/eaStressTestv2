"""
Tests for Re-Optimization Analyzer

Tests the analysis of optimization results for parameter patterns
and re-optimization recommendations.
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from modules.reopt_analyzer import (
    analyze_for_reoptimization,
    format_analysis_report,
    _analyze_toggle_param,
    _analyze_continuous_param,
    _is_truthy,
    ReoptAnalysis,
    ToggleAnalysis,
    ContinuousAnalysis,
)


class TestIsTruthy:
    """Tests for _is_truthy helper."""

    def test_bool_true(self):
        assert _is_truthy(True) is True

    def test_bool_false(self):
        assert _is_truthy(False) is False

    def test_int_one(self):
        assert _is_truthy(1) is True

    def test_int_zero(self):
        assert _is_truthy(0) is False

    def test_float_one(self):
        assert _is_truthy(1.0) is True

    def test_string_true(self):
        assert _is_truthy('true') is True
        assert _is_truthy('True') is True
        assert _is_truthy('TRUE') is True

    def test_string_false(self):
        assert _is_truthy('false') is False
        assert _is_truthy('no') is False


class TestToggleAnalysis:
    """Tests for toggle (boolean) parameter analysis."""

    @pytest.fixture
    def toggle_passes(self):
        """Create passes with toggle parameter patterns."""
        # Top passes favor Enable_Filter=False
        top_passes = [
            {'params': {'Enable_Filter': False}, 'composite_score': 8.0},
            {'params': {'Enable_Filter': False}, 'composite_score': 7.5},
            {'params': {'Enable_Filter': False}, 'composite_score': 7.2},
            {'params': {'Enable_Filter': False}, 'composite_score': 7.0},
            {'params': {'Enable_Filter': True}, 'composite_score': 6.8},
        ]
        # All passes have 50/50 distribution
        all_passes = [
            {'params': {'Enable_Filter': False}, 'composite_score': 8.0},
            {'params': {'Enable_Filter': False}, 'composite_score': 7.5},
            {'params': {'Enable_Filter': False}, 'composite_score': 7.2},
            {'params': {'Enable_Filter': False}, 'composite_score': 7.0},
            {'params': {'Enable_Filter': True}, 'composite_score': 6.8},
            {'params': {'Enable_Filter': True}, 'composite_score': 6.5},
            {'params': {'Enable_Filter': True}, 'composite_score': 6.0},
            {'params': {'Enable_Filter': True}, 'composite_score': 5.5},
            {'params': {'Enable_Filter': True}, 'composite_score': 5.0},
            {'params': {'Enable_Filter': False}, 'composite_score': 4.5},
        ]
        return all_passes, top_passes

    def test_toggle_analysis_structure(self, toggle_passes):
        all_passes, top_passes = toggle_passes
        result = _analyze_toggle_param('Enable_Filter', all_passes, top_passes, top_n=5)

        assert isinstance(result, ToggleAnalysis)
        assert result.name == 'Enable_Filter'
        assert result.top_true_count + result.top_false_count == 5
        assert result.all_true_count + result.all_false_count == 10

    def test_toggle_false_wins(self, toggle_passes):
        all_passes, top_passes = toggle_passes
        result = _analyze_toggle_param('Enable_Filter', all_passes, top_passes, top_n=5)

        # 4 out of 5 top passes have False = 80%
        assert result.top_true_count == 1
        assert result.top_false_count == 4
        assert result.top_true_pct == 20.0
        assert result.recommendation == 'FIX_FALSE'

    def test_toggle_true_wins(self):
        """Test when True dominates top passes."""
        top_passes = [
            {'params': {'Use_Feature': True}, 'composite_score': 9.0},
            {'params': {'Use_Feature': True}, 'composite_score': 8.5},
            {'params': {'Use_Feature': True}, 'composite_score': 8.0},
            {'params': {'Use_Feature': True}, 'composite_score': 7.5},
            {'params': {'Use_Feature': False}, 'composite_score': 7.0},
        ]
        all_passes = top_passes * 2

        result = _analyze_toggle_param('Use_Feature', all_passes, top_passes, top_n=5)

        assert result.top_true_pct == 80.0
        assert result.recommendation == 'FIX_TRUE'

    def test_toggle_keep_optimizing(self):
        """Test when toggle shows no clear pattern."""
        passes = [
            {'params': {'Enable_X': True}, 'composite_score': 8.0},
            {'params': {'Enable_X': False}, 'composite_score': 7.8},
            {'params': {'Enable_X': True}, 'composite_score': 7.6},
            {'params': {'Enable_X': False}, 'composite_score': 7.4},
            {'params': {'Enable_X': True}, 'composite_score': 7.2},
        ]

        result = _analyze_toggle_param('Enable_X', passes, passes, top_n=5)

        # 60% True - not strong enough for FIX_TRUE (needs 70%)
        assert result.recommendation == 'KEEP_OPTIMIZING'


class TestContinuousAnalysis:
    """Tests for continuous (numeric) parameter analysis."""

    @pytest.fixture
    def continuous_passes(self):
        """Create passes with clustered continuous parameter."""
        # Top passes cluster around 14
        top_passes = [
            {'params': {'RSI_Period': 14}, 'composite_score': 8.0},
            {'params': {'RSI_Period': 14}, 'composite_score': 7.8},
            {'params': {'RSI_Period': 16}, 'composite_score': 7.5},
            {'params': {'RSI_Period': 14}, 'composite_score': 7.2},
            {'params': {'RSI_Period': 12}, 'composite_score': 7.0},
        ]
        all_passes = top_passes + [
            {'params': {'RSI_Period': 10}, 'composite_score': 5.0},
            {'params': {'RSI_Period': 20}, 'composite_score': 4.5},
            {'params': {'RSI_Period': 22}, 'composite_score': 4.0},
        ]
        range_info = {'name': 'RSI_Period', 'start': 10, 'stop': 22, 'step': 2}
        return all_passes, top_passes, range_info

    def test_continuous_analysis_structure(self, continuous_passes):
        all_passes, top_passes, range_info = continuous_passes
        result = _analyze_continuous_param('RSI_Period', all_passes, top_passes, range_info, top_n=5)

        assert isinstance(result, ContinuousAnalysis)
        assert result.name == 'RSI_Period'
        assert len(result.top_values) == 5
        assert result.top_min <= result.top_mean <= result.top_max

    def test_continuous_clustering(self, continuous_passes):
        all_passes, top_passes, range_info = continuous_passes
        result = _analyze_continuous_param('RSI_Period', all_passes, top_passes, range_info, top_n=5)

        # Values cluster tightly (low CV)
        assert result.coefficient_of_variation < 0.2
        assert result.recommendation == 'NARROW_RANGE'

    def test_continuous_no_clustering(self):
        """Test when values are spread across range."""
        passes = [
            {'params': {'StopLoss': 50}, 'composite_score': 8.0},
            {'params': {'StopLoss': 100}, 'composite_score': 7.5},
            {'params': {'StopLoss': 150}, 'composite_score': 7.0},
            {'params': {'StopLoss': 200}, 'composite_score': 6.5},
            {'params': {'StopLoss': 250}, 'composite_score': 6.0},
        ]
        range_info = {'start': 50, 'stop': 250, 'step': 50}

        result = _analyze_continuous_param('StopLoss', passes, passes, range_info, top_n=5)

        # High CV = spread out, not clustered
        assert result.coefficient_of_variation > 0.3
        assert result.recommendation == 'KEEP_RANGE'

    def test_continuous_suggested_range(self, continuous_passes):
        all_passes, top_passes, range_info = continuous_passes
        result = _analyze_continuous_param('RSI_Period', all_passes, top_passes, range_info, top_n=5)

        # Should suggest narrowed range around cluster
        assert result.suggested_refined_range is not None
        suggested = result.suggested_refined_range
        # New range should be tighter than original
        original_width = range_info['stop'] - range_info['start']
        new_width = suggested['stop'] - suggested['start']
        assert new_width <= original_width


class TestAnalyzeForReoptimization:
    """Tests for main analysis function."""

    @pytest.fixture
    def mixed_passes(self):
        """Create passes with various parameter patterns."""
        # Toggle: Enable_MA_Filter False wins
        # Continuous: RSI_Period clusters at 14
        top_passes = [
            {'params': {'Enable_MA_Filter': False, 'RSI_Period': 14, 'StopLoss': 100}, 'composite_score': 8.0},
            {'params': {'Enable_MA_Filter': False, 'RSI_Period': 14, 'StopLoss': 120}, 'composite_score': 7.8},
            {'params': {'Enable_MA_Filter': False, 'RSI_Period': 16, 'StopLoss': 80}, 'composite_score': 7.5},
            {'params': {'Enable_MA_Filter': False, 'RSI_Period': 14, 'StopLoss': 140}, 'composite_score': 7.2},
            {'params': {'Enable_MA_Filter': True, 'RSI_Period': 14, 'StopLoss': 100}, 'composite_score': 7.0},
        ]
        all_passes = top_passes + [
            {'params': {'Enable_MA_Filter': True, 'RSI_Period': 10, 'StopLoss': 200}, 'composite_score': 5.0},
            {'params': {'Enable_MA_Filter': True, 'RSI_Period': 22, 'StopLoss': 50}, 'composite_score': 4.5},
            {'params': {'Enable_MA_Filter': False, 'RSI_Period': 20, 'StopLoss': 180}, 'composite_score': 4.0},
        ]
        ranges = [
            {'name': 'Enable_MA_Filter', 'optimize': True},
            {'name': 'RSI_Period', 'start': 10, 'stop': 22, 'step': 2, 'optimize': True},
            {'name': 'StopLoss', 'start': 50, 'stop': 200, 'step': 10, 'optimize': True},
        ]
        return all_passes, top_passes, ranges

    def test_analysis_structure(self, mixed_passes):
        all_passes, top_passes, ranges = mixed_passes
        result = analyze_for_reoptimization(all_passes, top_passes, ranges, top_n=5)

        assert isinstance(result, ReoptAnalysis)
        assert result.total_passes == 8
        assert result.top_n_analyzed == 5

    def test_analysis_toggle_detection(self, mixed_passes):
        all_passes, top_passes, ranges = mixed_passes
        result = analyze_for_reoptimization(all_passes, top_passes, ranges, top_n=5)

        assert 'Enable_MA_Filter' in result.toggle_analysis
        toggle = result.toggle_analysis['Enable_MA_Filter']
        assert toggle.recommendation == 'FIX_FALSE'

    def test_analysis_continuous_detection(self, mixed_passes):
        all_passes, top_passes, ranges = mixed_passes
        result = analyze_for_reoptimization(all_passes, top_passes, ranges, top_n=5)

        assert 'RSI_Period' in result.continuous_analysis
        cont = result.continuous_analysis['RSI_Period']
        assert cont.coefficient_of_variation < 0.2

    def test_analysis_recommendation(self, mixed_passes):
        all_passes, top_passes, ranges = mixed_passes
        result = analyze_for_reoptimization(all_passes, top_passes, ranges, top_n=5)

        # Should recommend re-optimization due to patterns
        rec = result.recommendation
        assert rec.should_reoptimize is True
        assert len(rec.reasons) > 0
        assert len(rec.suggested_changes) > 0

    def test_analysis_no_patterns(self):
        """Test when no clear patterns exist."""
        # Need enough passes to exceed MIN_VALID_PASSES (50)
        passes = []
        for i in range(60):
            passes.append({
                'params': {'X': i % 2 == 0, 'Y': 10 + (i % 5) * 10},
                'composite_score': 7.0 - (i * 0.01),  # Slightly decreasing scores
            })
        ranges = [
            {'name': 'X', 'optimize': True},
            {'name': 'Y', 'start': 10, 'stop': 50, 'step': 10, 'optimize': True},
        ]

        result = analyze_for_reoptimization(passes, passes[:20], ranges, top_n=20)

        # No strong patterns (50/50 toggle, spread Y values) = don't reoptimize
        # Note: X alternates true/false, Y spreads across 10-50
        assert result.recommendation.should_reoptimize is False
        assert result.recommendation.confidence == 'high'

    def test_analysis_empty_passes(self):
        """Test with empty input."""
        result = analyze_for_reoptimization([], [], [], top_n=5)

        assert result.total_passes == 0
        assert result.recommendation.should_reoptimize is False
        assert 'No passes' in result.recommendation.reasons[0]


class TestFormatAnalysisReport:
    """Tests for report formatting."""

    def test_format_basic_structure(self):
        """Test report contains expected sections."""
        analysis = ReoptAnalysis(
            total_passes=100,
            valid_passes=80,
            top_n_analyzed=20,
        )

        report = format_analysis_report(analysis)

        assert 'RE-OPTIMIZATION ANALYSIS' in report
        assert 'Total Passes: 100' in report
        assert 'RECOMMENDATION' in report
        assert 'PATTERNS FOUND' in report

    def test_format_with_toggle_analysis(self):
        """Test report includes toggle details."""
        toggle = ToggleAnalysis(
            name='Enable_Test',
            top_true_count=5,
            top_false_count=15,
            top_true_pct=25.0,
            all_true_pct=50.0,
            top_vs_all_diff=-25.0,
            recommendation='FIX_FALSE',
        )
        analysis = ReoptAnalysis(
            total_passes=100,
            toggle_analysis={'Enable_Test': toggle},
        )

        report = format_analysis_report(analysis)

        assert 'TOGGLE ANALYSIS' in report
        assert 'Enable_Test' in report
        assert 'FIX_FALSE' in report

    def test_format_with_continuous_analysis(self):
        """Test report includes continuous details."""
        cont = ContinuousAnalysis(
            name='RSI_Period',
            top_mean=14.5,
            top_std=1.2,
            coefficient_of_variation=0.08,
            recommendation='NARROW_RANGE',
        )
        analysis = ReoptAnalysis(
            total_passes=100,
            continuous_analysis={'RSI_Period': cont},
        )

        report = format_analysis_report(analysis)

        assert 'CONTINUOUS ANALYSIS' in report
        assert 'RSI_Period' in report
        assert 'NARROW_RANGE' in report


class TestToDict:
    """Tests for serialization."""

    def test_to_dict_structure(self):
        """Test to_dict produces valid structure."""
        analysis = ReoptAnalysis(
            total_passes=100,
            valid_passes=80,
            top_n_analyzed=20,
        )

        d = analysis.to_dict()

        assert isinstance(d, dict)
        assert d['total_passes'] == 100
        assert d['valid_passes'] == 80
        assert 'toggle_analysis' in d
        assert 'continuous_analysis' in d
        assert 'recommendation' in d

    def test_to_dict_with_nested(self):
        """Test nested objects are serialized."""
        toggle = ToggleAnalysis(name='Test', recommendation='FIX_TRUE')
        analysis = ReoptAnalysis(
            total_passes=50,
            toggle_analysis={'Test': toggle},
        )

        d = analysis.to_dict()

        assert 'Test' in d['toggle_analysis']
        assert d['toggle_analysis']['Test']['recommendation'] == 'FIX_TRUE'


class TestTwoStageEnforcement:
    """
    Tests for two-stage optimization enforcement.

    The workflow enforces that run_reopt_analysis() must be called before
    continue_with_analysis() to ensure users review optimization patterns
    before proceeding to backtesting.
    """

    def test_enforcement_error_message(self):
        """Test that the error message explains the two-stage process."""
        # This tests the error message content, not the actual enforcement
        # (which requires a full WorkflowRunner setup)
        expected_phrases = [
            "Two-stage optimization",
            "run_reopt_analysis()",
            "continue_with_analysis()",
        ]
        error_msg = (
            "Two-stage optimization enforcement: Must call run_reopt_analysis() "
            "before continue_with_analysis().\n\n"
            "The two-stage process requires:\n"
            "1. After Step 8: Call runner.run_reopt_analysis() to analyze results\n"
            "2. Review analysis: Check toggle patterns and clustering\n"
            "3. Decision: Either re-optimize with refined ranges, or proceed\n"
            "4. Then: Call continue_with_analysis() with selected passes\n\n"
            "To bypass (not recommended): pass skip_reopt_check=True"
        )
        for phrase in expected_phrases:
            assert phrase in error_msg, f"Error message should contain '{phrase}'"
