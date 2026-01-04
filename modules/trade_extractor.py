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
    # Extended fields for enhanced dashboard
    mfe: float = 0.0  # Maximum Favorable Excursion (best unrealized profit)
    mae: float = 0.0  # Maximum Adverse Excursion (worst unrealized loss)
    holding_seconds: int = 0  # Holding time in seconds

    @property
    def holding_time_str(self) -> str:
        """Return holding time as human-readable string."""
        if self.holding_seconds <= 0:
            return "0:00:00"
        hours, remainder = divmod(self.holding_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours >= 24:
            days, hours = divmod(hours, 24)
            return f"{days}d {hours}:{minutes:02d}:{seconds:02d}"
        return f"{hours}:{minutes:02d}:{seconds:02d}"


@dataclass
class TradeExtractionResult:
    """Result of extracting trades from an MT5 HTML report."""
    success: bool
    trades: List[Trade] = field(default_factory=list)
    initial_balance: float = 0.0
    final_balance: float = 0.0
    total_net_profit: float = 0.0
    total_commission: float = 0.0
    total_swap: float = 0.0
    error: Optional[str] = None

    def __post_init__(self):
        """Calculate totals from trades if not set."""
        if self.trades and self.total_net_profit == 0:
            self.total_net_profit = sum(t.net_profit for t in self.trades)
            self.total_commission = sum(t.commission for t in self.trades)
            self.total_swap = sum(t.swap for t in self.trades)


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

    # Track open positions to match with closes.
    # NOTE: In MT5, commissions are often charged on ENTRY deals, while Profit is realized on EXIT deals.
    # We must carry entry commission/swap into the resulting closed-trade record, otherwise PnL/commission
    # totals (and equity curve) won't match the MT5 "Total Net Profit".
    open_positions: list[dict] = []

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
                if direction == 'inout':
                    # Complete trade in one deal (rare). Treat as a closed trade and DO NOT
                    # keep an open position record.
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
                else:
                    # Opening position: store remaining volume and costs so they can be
                    # allocated to later closing deals (supports partial closes).
                    open_positions.append({
                        'ticket': ticket,
                        'symbol': symbol,
                        'trade_type': deal_type,  # 'buy' or 'sell' position direction
                        'open_volume': volume,
                        'remaining_volume': volume,
                        'open_time': deal_time,
                        'open_price': price,
                        'remaining_commission': commission,
                        'remaining_swap': swap,
                        'remaining_profit': profit,  # usually 0 on entry, but keep for completeness
                    })

            elif direction == 'out':
                # Closing deal. In MT5, the close deal ticket usually does NOT match the entry
                # ticket, and partial closes are represented as multiple 'out' deals.
                close_volume = volume
                close_comm = commission
                close_swap = swap
                close_profit = profit

                # Close deals are the opposite side of the open position:
                #   - sell out closes a buy position
                #   - buy out closes a sell position
                if deal_type == 'sell':
                    expected_open_type = 'buy'
                elif deal_type == 'buy':
                    expected_open_type = 'sell'
                else:
                    expected_open_type = None

                open_pos = None
                open_idx = None

                # Prefer matching by symbol + expected open type (FIFO). Fall back to symbol-only.
                if expected_open_type:
                    for idx, pos in enumerate(open_positions):
                        if pos.get('symbol') == symbol and pos.get('trade_type') == expected_open_type:
                            open_pos = pos
                            open_idx = idx
                            break

                if open_pos is None:
                    for idx, pos in enumerate(open_positions):
                        if pos.get('symbol') == symbol:
                            open_pos = pos
                            open_idx = idx
                            break

                if open_pos is None:
                    # No matching open found: treat as a standalone close deal (still include costs)
                    trades.append(Trade(
                        ticket=ticket,
                        symbol=symbol,
                        trade_type=expected_open_type or deal_type,
                        volume=close_volume,
                        open_time=deal_time,
                        close_time=deal_time,
                        open_price=price,
                        close_price=price,
                        commission=close_comm,
                        swap=close_swap,
                        gross_profit=close_profit,
                        net_profit=close_profit + close_comm + close_swap,
                    ))
                    final_balance = balance
                    continue

                # Allocate remaining entry costs proportionally for partial closes.
                remaining_vol = float(open_pos.get('remaining_volume') or 0.0)
                if remaining_vol <= 0:
                    remaining_vol = float(open_pos.get('open_volume') or 0.0) or 0.0

                remaining_commission = float(open_pos.get('remaining_commission') or 0.0)
                remaining_swap = float(open_pos.get('remaining_swap') or 0.0)
                remaining_profit = float(open_pos.get('remaining_profit') or 0.0)

                # If this deal closes the position (or effectively closes it due to floating-point
                # rounding), allocate *all* remaining entry costs to this close so totals reconcile.
                is_final_close = remaining_vol > 0 and close_volume >= (remaining_vol - 1e-9)

                if is_final_close:
                    alloc_comm = remaining_commission
                    alloc_swap = remaining_swap
                    alloc_profit = remaining_profit
                    open_pos['remaining_volume'] = 0.0
                    open_pos['remaining_commission'] = 0.0
                    open_pos['remaining_swap'] = 0.0
                    open_pos['remaining_profit'] = 0.0
                    if open_idx is not None:
                        open_positions.pop(open_idx)
                else:
                    frac = 1.0
                    if remaining_vol > 0 and close_volume > 0:
                        frac = min(1.0, max(0.0, close_volume / remaining_vol))

                    alloc_comm = remaining_commission * frac
                    alloc_swap = remaining_swap * frac
                    alloc_profit = remaining_profit * frac

                    # Update open position remaining amounts
                    open_pos['remaining_volume'] = max(0.0, remaining_vol - close_volume)
                    open_pos['remaining_commission'] = remaining_commission - alloc_comm
                    open_pos['remaining_swap'] = remaining_swap - alloc_swap
                    open_pos['remaining_profit'] = remaining_profit - alloc_profit

                gross_profit = close_profit + alloc_profit
                total_comm = close_comm + alloc_comm
                total_swap = close_swap + alloc_swap

                trades.append(Trade(
                    ticket=ticket,
                    symbol=symbol,
                    trade_type=open_pos.get('trade_type') or expected_open_type or deal_type,
                    volume=close_volume,
                    open_time=open_pos.get('open_time', deal_time),
                    close_time=deal_time,
                    open_price=open_pos.get('open_price', price),
                    close_price=price,
                    commission=total_comm,
                    swap=total_swap,
                    gross_profit=gross_profit,
                    net_profit=gross_profit + total_comm + total_swap,
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


def compute_holding_time_seconds(open_time: datetime, close_time: datetime) -> int:
    """Calculate holding time in seconds."""
    if open_time and close_time and close_time > open_time:
        delta = close_time - open_time
        return int(delta.total_seconds())
    return 0


def generate_profit_histogram(trades: List[Trade], bucket_count: int = 20) -> dict:
    """
    Generate profit distribution histogram data for Chart.js.

    Returns:
        Dict with 'labels' (bucket ranges) and 'values' (counts)
    """
    if not trades:
        return {'labels': [], 'values': [], 'colors': []}

    profits = [t.net_profit for t in trades]
    min_profit = min(profits)
    max_profit = max(profits)

    if min_profit == max_profit:
        return {
            'labels': [f'{min_profit:.0f}'],
            'values': [len(profits)],
            'colors': ['#198754' if min_profit >= 0 else '#dc3545']
        }

    # Create buckets
    bucket_size = (max_profit - min_profit) / bucket_count
    buckets = [0] * bucket_count
    labels = []
    colors = []

    for i in range(bucket_count):
        bucket_min = min_profit + i * bucket_size
        bucket_max = bucket_min + bucket_size
        labels.append(f'{bucket_min:.0f}')
        # Color: green for positive buckets, red for negative
        mid = (bucket_min + bucket_max) / 2
        colors.append('#198754' if mid >= 0 else '#dc3545')

    for profit in profits:
        bucket_idx = int((profit - min_profit) / bucket_size)
        bucket_idx = min(bucket_idx, bucket_count - 1)  # Handle edge case
        buckets[bucket_idx] += 1

    return {
        'labels': labels,
        'values': buckets,
        'colors': colors,
        'min': min_profit,
        'max': max_profit,
    }


def generate_mfe_mae_scatter(trades: List[Trade]) -> List[dict]:
    """
    Generate MFE/MAE scatter plot data for Chart.js.

    If MFE/MAE not available, estimate from trade profit as:
    - MFE: max(profit, 0) for winning trades
    - MAE: min(profit, 0) for losing trades

    Returns:
        List of {x: MAE, y: MFE, profit: net_profit} dicts
    """
    data = []
    for t in trades:
        # If MFE/MAE stored, use them; otherwise estimate
        mfe = t.mfe if t.mfe != 0 else max(t.net_profit, 0)
        mae = t.mae if t.mae != 0 else min(t.net_profit, 0)

        data.append({
            'x': mae,  # MAE (negative or zero)
            'y': mfe,  # MFE (positive or zero)
            'profit': t.net_profit,
        })
    return data


def generate_holding_time_distribution(trades: List[Trade], bucket_count: int = 10) -> dict:
    """
    Generate holding time distribution histogram data for Chart.js.

    Returns:
        Dict with 'labels' (time ranges) and 'values' (counts)
    """
    if not trades:
        return {'labels': [], 'values': []}

    # Calculate holding times if not already set
    holding_times = []
    for t in trades:
        if t.holding_seconds > 0:
            holding_times.append(t.holding_seconds)
        elif t.open_time and t.close_time:
            seconds = compute_holding_time_seconds(t.open_time, t.close_time)
            holding_times.append(seconds)

    if not holding_times:
        return {'labels': [], 'values': []}

    min_time = min(holding_times)
    max_time = max(holding_times)

    if min_time == max_time:
        return {
            'labels': [_format_duration(min_time)],
            'values': [len(holding_times)]
        }

    # Create buckets
    bucket_size = (max_time - min_time) / bucket_count
    if bucket_size == 0:
        bucket_size = 1
    buckets = [0] * bucket_count
    labels = []

    for i in range(bucket_count):
        bucket_start = min_time + i * bucket_size
        labels.append(_format_duration(bucket_start))

    for ht in holding_times:
        bucket_idx = int((ht - min_time) / bucket_size)
        bucket_idx = min(bucket_idx, bucket_count - 1)
        buckets[bucket_idx] += 1

    return {
        'labels': labels,
        'values': buckets,
        'min_seconds': min_time,
        'max_seconds': max_time,
    }


def _format_duration(seconds: int) -> str:
    """Format seconds into human readable duration."""
    if seconds < 60:
        return f'{seconds}s'
    elif seconds < 3600:
        return f'{seconds // 60}m'
    elif seconds < 86400:
        return f'{seconds // 3600}h'
    else:
        return f'{seconds // 86400}d'


def generate_chart_data(trades: List[Trade]) -> dict:
    """
    Generate all chart data for the dashboard.

    Returns dict with:
        - profit_histogram: Profit distribution
        - mfe_mae: MFE/MAE scatter data
        - holding_times: Holding time distribution
    """
    return {
        'profit_histogram': generate_profit_histogram(trades),
        'mfe_mae': generate_mfe_mae_scatter(trades),
        'holding_times': generate_holding_time_distribution(trades),
    }
