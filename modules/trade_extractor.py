"""
Trade extractor module for parsing MT5 HTML backtest reports.

Extracts individual trades from MT5 HTML reports and computes equity curves.
Used by dashboard to show top 20 passes with their equity curves.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class Trade:
    """Represents a single completed trade from MT5 report."""
    ticket: int
    symbol: str
    trade_type: str  # 'buy' or 'sell'
    volume: float
    open_time: datetime
    close_time: datetime
    open_price: float
    close_price: float
    commission: float = 0.0
    swap: float = 0.0
    gross_profit: float = 0.0
    net_profit: float = 0.0  # gross_profit + commission + swap


@dataclass
class TradeExtractionResult:
    """Result of extracting trades from an MT5 HTML report."""
    success: bool
    trades: List[Trade] = field(default_factory=list)
    initial_balance: float = 0.0
    final_balance: float = 0.0
    error: Optional[str] = None


def extract_trades(html_path: str) -> TradeExtractionResult:
    """
    Extract trades from MT5 HTML backtest report.

    Args:
        html_path: Path to the MT5 HTML report file

    Returns:
        TradeExtractionResult with success status and list of Trade objects
    """
    path = Path(html_path)

    if not path.exists():
        return TradeExtractionResult(
            success=False,
            error=f"File not found: {html_path}"
        )

    # Try different encodings - MT5 uses UTF-16-LE
    content = None
    for encoding in ['utf-16-le', 'utf-8', 'cp1252']:
        try:
            with open(path, 'r', encoding=encoding, errors='ignore') as f:
                content = f.read()
                if len(content) > 100:  # Basic sanity check
                    break
        except Exception:
            continue

    if not content:
        return TradeExtractionResult(
            success=False,
            error="Could not read file with any encoding"
        )

    return _parse_trades_from_html(content)


def _parse_trades_from_html(content: str) -> TradeExtractionResult:
    """Parse trades from MT5 HTML content."""
    trades = []
    initial_balance = 0.0
    final_balance = 0.0

    # Extract initial balance from "Initial Deposit" or first balance entry
    deposit_match = re.search(
        r'Initial [Dd]eposit:?[^<]*<[^>]*>([0-9.,\s]+)',
        content
    )
    if deposit_match:
        try:
            initial_balance = _parse_number(deposit_match.group(1))
        except:
            pass

    # Look for Deals table in MT5 report
    # MT5 reports have a table with headers: Time, Deal, Symbol, Type, Direction, Volume, Price, etc.
    deals_pattern = re.compile(
        r'<tr[^>]*>\s*'
        r'<td[^>]*>([^<]+)</td>\s*'  # Time
        r'<td[^>]*>(\d+)</td>\s*'    # Deal ticket
        r'<td[^>]*>([^<]*)</td>\s*'  # Symbol
        r'<td[^>]*>([^<]+)</td>\s*'  # Type (buy/sell/balance)
        r'<td[^>]*>([^<]*)</td>\s*'  # Direction (in/out/inout)
        r'<td[^>]*>([^<]*)</td>\s*'  # Volume
        r'<td[^>]*>([^<]*)</td>\s*'  # Price
        r'<td[^>]*>([^<]*)</td>\s*'  # Order
        r'<td[^>]*>([^<]*)</td>\s*'  # Commission
        r'<td[^>]*>([^<]*)</td>\s*'  # Swap
        r'<td[^>]*>([^<]*)</td>\s*'  # Profit
        r'<td[^>]*>([^<]*)</td>',    # Balance
        re.IGNORECASE | re.DOTALL
    )

    # Track open positions to match with closes
    open_positions = {}  # ticket -> deal info

    for match in deals_pattern.finditer(content):
        try:
            time_str = match.group(1).strip()
            ticket = int(match.group(2))
            symbol = match.group(3).strip()
            deal_type = match.group(4).strip().lower()
            direction = match.group(5).strip().lower()
            volume = _parse_number(match.group(6)) if match.group(6).strip() else 0.0
            price = _parse_number(match.group(7)) if match.group(7).strip() else 0.0
            commission = _parse_number(match.group(9)) if match.group(9).strip() else 0.0
            swap = _parse_number(match.group(10)) if match.group(10).strip() else 0.0
            profit = _parse_number(match.group(11)) if match.group(11).strip() else 0.0
            balance = _parse_number(match.group(12)) if match.group(12).strip() else 0.0

            # Parse time
            deal_time = _parse_datetime(time_str)

            # Skip balance operations
            if deal_type == 'balance':
                if initial_balance == 0:
                    initial_balance = balance
                final_balance = balance
                continue

            # Match opening and closing deals
            if direction in ('in', 'inout'):
                # Opening position
                open_positions[ticket] = {
                    'ticket': ticket,
                    'symbol': symbol,
                    'trade_type': deal_type,
                    'volume': volume,
                    'open_time': deal_time,
                    'open_price': price,
                }
                if direction == 'inout':
                    # Complete trade in one deal
                    trades.append(Trade(
                        ticket=ticket,
                        symbol=symbol,
                        trade_type=deal_type,
                        volume=volume,
                        open_time=deal_time,
                        close_time=deal_time,
                        open_price=price,
                        close_price=price,
                        commission=commission,
                        swap=swap,
                        gross_profit=profit,
                        net_profit=profit + commission + swap,
                    ))
                    final_balance = balance

            elif direction == 'out':
                # Closing position - find matching open
                # In MT5, the ticket for close might be different
                # We need to match by symbol and opposite type
                if ticket in open_positions:
                    open_pos = open_positions.pop(ticket)
                else:
                    # Try to find any open position for this symbol
                    for open_ticket, open_pos in list(open_positions.items()):
                        if open_pos['symbol'] == symbol:
                            open_positions.pop(open_ticket)
                            break
                    else:
                        # No matching open found, create partial trade
                        open_pos = {
                            'ticket': ticket,
                            'symbol': symbol,
                            'trade_type': deal_type,
                            'volume': volume,
                            'open_time': deal_time,
                            'open_price': price,
                        }

                trades.append(Trade(
                    ticket=open_pos['ticket'],
                    symbol=open_pos['symbol'],
                    trade_type=open_pos['trade_type'],
                    volume=open_pos['volume'],
                    open_time=open_pos['open_time'],
                    close_time=deal_time,
                    open_price=open_pos['open_price'],
                    close_price=price,
                    commission=commission,
                    swap=swap,
                    gross_profit=profit,
                    net_profit=profit + commission + swap,
                ))
                final_balance = balance

        except Exception as e:
            continue  # Skip malformed rows

    # If no deals found with the detailed pattern, try simpler extraction
    if not trades:
        trades, initial_balance, final_balance = _extract_trades_simple(content)

    # If still no trades, try to parse from Orders table
    if not trades:
        trades, initial_balance, final_balance = _extract_from_orders_table(content)

    if not trades:
        return TradeExtractionResult(
            success=False,
            error="No trades found in report",
            initial_balance=initial_balance
        )

    return TradeExtractionResult(
        success=True,
        trades=trades,
        initial_balance=initial_balance,
        final_balance=final_balance
    )


def _extract_trades_simple(content: str) -> tuple:
    """Simpler trade extraction for different report formats."""
    trades = []
    initial_balance = 0.0
    final_balance = 0.0

    # Look for rows with profit values in common table formats
    # Pattern: looking for rows with time, type, volume, price, profit
    row_pattern = re.compile(
        r'<tr[^>]*>.*?'
        r'(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})'  # Time
        r'.*?<td[^>]*>([^<]*(?:buy|sell)[^<]*)</td>'   # Type
        r'.*?<td[^>]*>([\d.,]+)</td>'                  # Volume
        r'.*?<td[^>]*>([\d.,]+)</td>'                  # Some price
        r'.*?<td[^>]*>([-\d.,\s]+)</td>'               # Profit
        r'.*?</tr>',
        re.IGNORECASE | re.DOTALL
    )

    ticket = 0
    for match in row_pattern.finditer(content):
        try:
            ticket += 1
            time_str = match.group(1)
            trade_type = 'buy' if 'buy' in match.group(2).lower() else 'sell'
            volume = _parse_number(match.group(3))
            price = _parse_number(match.group(4))
            profit = _parse_number(match.group(5))

            trade_time = _parse_datetime(time_str)

            trades.append(Trade(
                ticket=ticket,
                symbol='',  # Unknown in this format
                trade_type=trade_type,
                volume=volume,
                open_time=trade_time,
                close_time=trade_time,
                open_price=price,
                close_price=price,
                net_profit=profit,
                gross_profit=profit,
            ))
        except:
            continue

    return trades, initial_balance, final_balance


def _extract_from_orders_table(content: str) -> tuple:
    """Extract from MT5 Orders/History table."""
    trades = []
    initial_balance = 0.0
    final_balance = 0.0

    # Look for profit column values directly
    profit_pattern = re.compile(
        r'Profit:.*?<b>([-\d.,\s]+)</b>|'
        r'<td[^>]*class="[^"]*profit[^"]*"[^>]*>([-\d.,\s]+)</td>',
        re.IGNORECASE
    )

    # If we find individual trade profits in the report
    trade_profits = []
    for match in profit_pattern.finditer(content):
        profit_str = match.group(1) or match.group(2)
        if profit_str:
            try:
                profit = _parse_number(profit_str)
                if profit != 0:
                    trade_profits.append(profit)
            except:
                continue

    # Create synthetic trades from profits
    ticket = 0
    now = datetime.now()
    for profit in trade_profits:
        ticket += 1
        trades.append(Trade(
            ticket=ticket,
            symbol='',
            trade_type='buy' if profit > 0 else 'sell',
            volume=0.1,
            open_time=now,
            close_time=now,
            open_price=0,
            close_price=0,
            net_profit=profit,
            gross_profit=profit,
        ))

    return trades, initial_balance, final_balance


def _parse_number(value: str) -> float:
    """Parse a number from string, handling various formats."""
    if not value:
        return 0.0
    # Remove spaces and replace comma with dot for decimals
    cleaned = value.strip().replace(' ', '').replace('\xa0', '')
    # Handle European format (comma as decimal separator)
    if ',' in cleaned and '.' in cleaned:
        # Both present - assume comma is thousands separator
        cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        # Only comma - could be thousands or decimal
        # If only one comma and less than 3 digits after, it's decimal
        parts = cleaned.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    return float(cleaned)


def _parse_datetime(time_str: str) -> datetime:
    """Parse datetime from MT5 format."""
    time_str = time_str.strip()
    # MT5 formats: "2024.01.15 10:30:00" or "2024.01.15 10:30"
    for fmt in ['%Y.%m.%d %H:%M:%S', '%Y.%m.%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    # Return epoch if parsing fails
    return datetime(1970, 1, 1)


def compute_equity_curve(trades: List[Trade], initial_balance: float = 0.0) -> List[float]:
    """
    Compute equity curve from list of trades.

    Args:
        trades: List of Trade objects, should be sorted by close_time
        initial_balance: Starting balance

    Returns:
        List of equity values after each trade
    """
    if not trades:
        return [initial_balance] if initial_balance > 0 else []

    # Sort trades by close time
    sorted_trades = sorted(trades, key=lambda t: t.close_time)

    equity = [initial_balance]
    current_balance = initial_balance

    for trade in sorted_trades:
        current_balance += trade.net_profit
        equity.append(current_balance)

    return equity


def split_trades_by_date(
    trades: List[Trade],
    split_date: datetime
) -> tuple[List[Trade], List[Trade]]:
    """
    Split trades into before and after a given date.

    Args:
        trades: List of Trade objects
        split_date: Date to split on (trades on this date go to 'after')

    Returns:
        Tuple of (before_trades, after_trades)
    """
    before = []
    after = []

    for trade in trades:
        if trade.close_time < split_date:
            before.append(trade)
        else:
            after.append(trade)

    return before, after
