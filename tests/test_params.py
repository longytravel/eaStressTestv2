"""
Tests for Parameter Extractor

Tests extraction of input parameters from MQL5 source files.
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from modules.params import (
    extract_params,
    get_optimizable_params,
    format_params_table,
)
# NOTE: suggest_param_ranges was removed - Claude /param-analyzer does this now


class TestExtractParams:
    """Tests for parameter extraction."""

    def test_extract_basic_params(self, sample_ea_file):
        """Test extracting basic input parameters."""
        params = extract_params(str(sample_ea_file))

        assert len(params) >= 4
        names = [p['name'] for p in params]
        assert 'Period' in names
        assert 'LotSize' in names
        assert 'StopLoss' in names
        assert 'TakeProfit' in names

    def test_extract_param_types(self, sample_ea_file):
        """Test parameter types are correctly identified."""
        params = extract_params(str(sample_ea_file))

        period = next(p for p in params if p['name'] == 'Period')
        assert period['type'] == 'int'
        assert period['base_type'] == 'int'

        lot_size = next(p for p in params if p['name'] == 'LotSize')
        assert lot_size['type'] == 'double'
        assert lot_size['base_type'] == 'double'

    def test_extract_default_values(self, sample_ea_file):
        """Test default values are extracted."""
        params = extract_params(str(sample_ea_file))

        period = next(p for p in params if p['name'] == 'Period')
        assert period['default'] == '14'

        lot_size = next(p for p in params if p['name'] == 'LotSize')
        assert lot_size['default'] == '0.1'

    def test_extract_comments(self, sample_ea_file):
        """Test inline comments are extracted."""
        params = extract_params(str(sample_ea_file))

        period = next(p for p in params if p['name'] == 'Period')
        assert period['comment'] == 'Indicator period'

    def test_sinput_not_optimizable(self, sample_ea_file):
        """Test that sinput parameters are marked non-optimizable."""
        params = extract_params(str(sample_ea_file))

        comment = next(p for p in params if p['name'] == 'Comment')
        assert comment['optimizable'] == False

    def test_input_optimizable(self, sample_ea_file):
        """Test that numeric input parameters are optimizable."""
        params = extract_params(str(sample_ea_file))

        period = next(p for p in params if p['name'] == 'Period')
        assert period['optimizable'] == True

        lot_size = next(p for p in params if p['name'] == 'LotSize')
        assert lot_size['optimizable'] == True

    def test_enum_not_optimizable(self, sample_ea_file):
        """Test that enum parameters are not optimizable."""
        params = extract_params(str(sample_ea_file))

        timeframe = next(p for p in params if p['name'] == 'Timeframe')
        assert timeframe['base_type'] == 'enum'
        assert timeframe['optimizable'] == False

    def test_file_not_found(self, temp_dir):
        """Test error when file not found."""
        with pytest.raises(FileNotFoundError):
            extract_params(str(temp_dir / "nonexistent.mq5"))

    def test_line_numbers(self, sample_ea_file):
        """Test that line numbers are captured."""
        params = extract_params(str(sample_ea_file))

        for param in params:
            assert 'line' in param
            assert param['line'] > 0


class TestGetOptimizableParams:
    """Tests for filtering optimizable parameters."""

    def test_filter_optimizable(self, sample_ea_file):
        """Test that only optimizable params are returned."""
        params = get_optimizable_params(str(sample_ea_file))

        for param in params:
            assert param['optimizable'] == True

        names = [p['name'] for p in params]
        assert 'Comment' not in names  # sinput
        assert 'Timeframe' not in names  # enum


class TestFormatParamsTable:
    """Tests for parameter table formatting."""

    def test_format_table(self, sample_ea_file):
        """Test table formatting."""
        params = extract_params(str(sample_ea_file))
        table = format_params_table(params)

        assert 'Name' in table
        assert 'Type' in table
        assert 'Default' in table
        assert 'Period' in table
        assert 'Yes' in table or 'No' in table

    def test_format_empty(self):
        """Test formatting empty params."""
        table = format_params_table([])
        assert 'No input parameters' in table


# NOTE: TestSuggestParamRanges class removed - suggest_param_ranges was replaced
# by Claude's /param-analyzer skill which provides intelligent range suggestions
# based on EA context, not Python heuristics.


class TestEdgeCases:
    """Tests for edge cases in parameter extraction."""

    def test_no_params(self, temp_dir):
        """Test EA with no input parameters."""
        ea_code = '''
//+------------------------------------------------------------------+
//| No params EA                                                      |
//+------------------------------------------------------------------+
int OnInit() { return INIT_SUCCEEDED; }
void OnTick() {}
'''
        ea_path = temp_dir / "NoParams.mq5"
        ea_path.write_text(ea_code)

        params = extract_params(str(ea_path))
        assert params == []

    def test_param_no_default(self, temp_dir):
        """Test parameter without default value."""
        ea_code = '''
input int Period;
'''
        ea_path = temp_dir / "NoDefault.mq5"
        ea_path.write_text(ea_code)

        params = extract_params(str(ea_path))
        assert len(params) == 1
        assert params[0]['default'] is None

    def test_param_complex_type(self, temp_dir):
        """Test parameter with complex ENUM type."""
        ea_code = '''
input ENUM_MA_METHOD MA_Method = MODE_SMA;
input ENUM_APPLIED_PRICE Price = PRICE_CLOSE;
'''
        ea_path = temp_dir / "EnumParams.mq5"
        ea_path.write_text(ea_code)

        params = extract_params(str(ea_path))
        assert len(params) == 2
        for p in params:
            assert p['base_type'] == 'enum'
