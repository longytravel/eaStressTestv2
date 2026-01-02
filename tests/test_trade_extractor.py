"""Tests for trade_extractor module."""

import sys
from pathlib import Path
from datetime import datetime
import tempfile
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.trade_extractor import (
    Trade,
    TradeExtractionResult,
    extract_trades,
    compute_equity_curve,
    split_trades_by_date,
    _parse_number,
    _parse_datetime,
)


class TestTrade:
    """Test Trade dataclass."""

    def test_create_trade(self):
        """Test creating a Trade object."""
        trade = Trade(
            ticket=12345,
            symbol='EURUSD',
            trade_type='buy',
            volume=0.1,
            open_time=datetime(2024, 1, 15, 10, 30, 0),
            close_time=datetime(2024, 1, 15, 14, 45, 0),
            open_price=1.0850,
            close_price=1.0900,
            commission=-0.70,
            swap=0.0,
            gross_profit=50.0,
            net_profit=49.30,
        )

        assert trade.ticket == 12345
        assert trade.symbol == 'EURUSD'
        assert trade.trade_type == 'buy'
        assert trade.volume == 0.1
        assert trade.net_profit == 49.30

    def test_default_values(self):
        """Test Trade with default values."""
        trade = Trade(
            ticket=1,
            symbol='GBPUSD',
            trade_type='sell',
            volume=0.01,
            open_time=datetime.now(),
            close_time=datetime.now(),
            open_price=1.25,
            close_price=1.24,
        )

        assert trade.commission == 0.0
        assert trade.swap == 0.0
        assert trade.gross_profit == 0.0
        assert trade.net_profit == 0.0


class TestTradeExtractionResult:
    """Test TradeExtractionResult dataclass."""

    def test_successful_result(self):
        """Test successful extraction result."""
        trade = Trade(
            ticket=1,
            symbol='EURUSD',
            trade_type='buy',
            volume=0.1,
            open_time=datetime.now(),
            close_time=datetime.now(),
            open_price=1.0,
            close_price=1.01,
            net_profit=10.0,
        )

        result = TradeExtractionResult(
            success=True,
            trades=[trade],
            initial_balance=10000.0,
            final_balance=10010.0,
        )

        assert result.success
        assert len(result.trades) == 1
        assert result.initial_balance == 10000.0

    def test_failed_result(self):
        """Test failed extraction result."""
        result = TradeExtractionResult(
            success=False,
            error="File not found"
        )

        assert not result.success
        assert result.error == "File not found"
        assert result.trades == []


class TestParseNumber:
    """Test number parsing utility."""

    def test_simple_integer(self):
        assert _parse_number('1000') == 1000.0

    def test_decimal_dot(self):
        assert _parse_number('1234.56') == 1234.56

    def test_decimal_comma(self):
        assert _parse_number('1234,56') == 1234.56

    def test_thousands_space(self):
        assert _parse_number('1 234.56') == 1234.56

    def test_european_format(self):
        # Comma as decimal with 2 digits after
        assert _parse_number('1234,56') == 1234.56

    def test_negative_number(self):
        assert _parse_number('-50.25') == -50.25

    def test_empty_string(self):
        assert _parse_number('') == 0.0

    def test_whitespace(self):
        assert _parse_number('  100.50  ') == 100.50


class TestParseDatetime:
    """Test datetime parsing utility."""

    def test_mt5_format(self):
        dt = _parse_datetime('2024.01.15 10:30:00')
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30

    def test_mt5_format_no_seconds(self):
        dt = _parse_datetime('2024.01.15 10:30')
        assert dt.year == 2024
        assert dt.minute == 30

    def test_iso_format(self):
        dt = _parse_datetime('2024-01-15 10:30:00')
        assert dt.year == 2024
        assert dt.month == 1

    def test_invalid_format(self):
        dt = _parse_datetime('invalid')
        assert dt == datetime(1970, 1, 1)


class TestExtractTrades:
    """Test extract_trades function."""

    def test_file_not_found(self):
        """Test extraction from non-existent file."""
        result = extract_trades('/nonexistent/path.html')
        assert not result.success
        assert 'not found' in result.error.lower()

    def test_empty_file(self):
        """Test extraction from empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write('')
            temp_path = f.name

        result = extract_trades(temp_path)
        assert not result.success
        Path(temp_path).unlink()

    def test_html_with_no_trades(self):
        """Test extraction from HTML with no trade data."""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Report</title></head>
        <body>
        <p>No trades here</p>
        </body>
        </html>
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html_content)
            temp_path = f.name

        result = extract_trades(temp_path)
        assert not result.success
        Path(temp_path).unlink()


class TestComputeEquityCurve:
    """Test compute_equity_curve function."""

    def test_empty_trades(self):
        """Test with no trades."""
        curve = compute_equity_curve([], 10000.0)
        assert curve == [10000.0]

    def test_single_winning_trade(self):
        """Test with single winning trade."""
        trade = Trade(
            ticket=1,
            symbol='EURUSD',
            trade_type='buy',
            volume=0.1,
            open_time=datetime(2024, 1, 1),
            close_time=datetime(2024, 1, 2),
            open_price=1.0,
            close_price=1.01,
            net_profit=100.0,
        )

        curve = compute_equity_curve([trade], 10000.0)
        assert curve == [10000.0, 10100.0]

    def test_multiple_trades(self):
        """Test with multiple trades."""
        trades = [
            Trade(
                ticket=1, symbol='EURUSD', trade_type='buy', volume=0.1,
                open_time=datetime(2024, 1, 1), close_time=datetime(2024, 1, 2),
                open_price=1.0, close_price=1.01, net_profit=100.0,
            ),
            Trade(
                ticket=2, symbol='EURUSD', trade_type='sell', volume=0.1,
                open_time=datetime(2024, 1, 3), close_time=datetime(2024, 1, 4),
                open_price=1.01, close_price=1.005, net_profit=-50.0,
            ),
            Trade(
                ticket=3, symbol='EURUSD', trade_type='buy', volume=0.2,
                open_time=datetime(2024, 1, 5), close_time=datetime(2024, 1, 6),
                open_price=1.005, close_price=1.015, net_profit=200.0,
            ),
        ]

        curve = compute_equity_curve(trades, 10000.0)
        assert curve == [10000.0, 10100.0, 10050.0, 10250.0]

    def test_trades_sorted_by_close_time(self):
        """Test that trades are sorted by close time."""
        trades = [
            Trade(
                ticket=2, symbol='EURUSD', trade_type='buy', volume=0.1,
                open_time=datetime(2024, 1, 5), close_time=datetime(2024, 1, 6),
                open_price=1.0, close_price=1.01, net_profit=200.0,
            ),
            Trade(
                ticket=1, symbol='EURUSD', trade_type='buy', volume=0.1,
                open_time=datetime(2024, 1, 1), close_time=datetime(2024, 1, 2),
                open_price=1.0, close_price=1.01, net_profit=100.0,
            ),
        ]

        curve = compute_equity_curve(trades, 10000.0)
        # Should be sorted: ticket 1 first (closes earlier), then ticket 2
        assert curve == [10000.0, 10100.0, 10300.0]


class TestSplitTradesByDate:
    """Test split_trades_by_date function."""

    def test_all_before(self):
        """Test when all trades are before split date."""
        trades = [
            Trade(
                ticket=1, symbol='EURUSD', trade_type='buy', volume=0.1,
                open_time=datetime(2024, 1, 1), close_time=datetime(2024, 1, 2),
                open_price=1.0, close_price=1.01, net_profit=100.0,
            ),
        ]

        before, after = split_trades_by_date(trades, datetime(2025, 1, 1))
        assert len(before) == 1
        assert len(after) == 0

    def test_all_after(self):
        """Test when all trades are after split date."""
        trades = [
            Trade(
                ticket=1, symbol='EURUSD', trade_type='buy', volume=0.1,
                open_time=datetime(2024, 6, 1), close_time=datetime(2024, 6, 2),
                open_price=1.0, close_price=1.01, net_profit=100.0,
            ),
        ]

        before, after = split_trades_by_date(trades, datetime(2024, 1, 1))
        assert len(before) == 0
        assert len(after) == 1

    def test_split_in_middle(self):
        """Test splitting trades in the middle."""
        trades = [
            Trade(
                ticket=1, symbol='EURUSD', trade_type='buy', volume=0.1,
                open_time=datetime(2024, 1, 1), close_time=datetime(2024, 3, 1),
                open_price=1.0, close_price=1.01, net_profit=100.0,
            ),
            Trade(
                ticket=2, symbol='EURUSD', trade_type='buy', volume=0.1,
                open_time=datetime(2024, 6, 1), close_time=datetime(2024, 8, 1),
                open_price=1.0, close_price=1.01, net_profit=200.0,
            ),
            Trade(
                ticket=3, symbol='EURUSD', trade_type='buy', volume=0.1,
                open_time=datetime(2024, 10, 1), close_time=datetime(2024, 12, 1),
                open_price=1.0, close_price=1.01, net_profit=300.0,
            ),
        ]

        # Split at July 1: ticket 1 closes March (before), tickets 2,3 close Aug/Dec (after)
        before, after = split_trades_by_date(trades, datetime(2024, 7, 1))
        assert len(before) == 1  # ticket 1 (closes March)
        assert len(after) == 2   # tickets 2 and 3 (close after July)

    def test_empty_trades(self):
        """Test with no trades."""
        before, after = split_trades_by_date([], datetime(2024, 6, 1))
        assert before == []
        assert after == []
