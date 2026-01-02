"""
EA Backtest Module

Runs single backtests using MT5 terminal.
Always uses: 4 years (3+1), 1-minute OHLC, 10ms latency.
"""
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.terminals import TerminalRegistry
import settings


def create_backtest_ini(
    ea_name: str,
    symbol: str,
    timeframe: str,
    params: Optional[dict] = None,
    output_path: Optional[str] = None,
    terminal: Optional[dict] = None,
) -> str:
    """
    Create an INI file for running a backtest.

    Args:
        ea_name: EA filename without path (e.g., "MyEA.ex5")
        symbol: Trading symbol (e.g., "EURUSD")
        timeframe: Timeframe (e.g., "H1", "M15")
        params: Dict of parameter name -> value overrides
        output_path: Where to save the INI file
        terminal: Terminal config dict

    Returns:
        Path to created INI file
    """
    if terminal is None:
        registry = TerminalRegistry()
        terminal = registry.get_terminal()

    # Get dynamic dates
    dates = settings.get_backtest_dates()

    # Convert timeframe to MT5 format
    tf_map = {
        'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
        'H1': 60, 'H4': 240, 'D1': 1440, 'W1': 10080, 'MN1': 43200
    }
    tf_value = tf_map.get(timeframe.upper(), 60)

    # Generate report name from EA name
    ea_base = Path(ea_name).stem
    report_name = f'{ea_base}_BT'

    # Build INI content
    ini_lines = [
        '; EA Stress Test - Backtest Configuration',
        f'; Generated: {datetime.now().isoformat()}',
        '',
        '[Tester]',
        f'Expert={ea_name}',
        f'Symbol={symbol}',
        f'Period={tf_value}',
        f'FromDate={dates["start"]}',
        f'ToDate={dates["end"]}',
        f'Model={settings.DATA_MODEL}',  # 1 = 1-minute OHLC
        f'ExecutionMode={settings.EXECUTION_LATENCY_MS}',
        'Optimization=0',  # 0 = disabled for single backtest
        'ForwardMode=0',
        f'Report={report_name}',
        'ReplaceReport=1',
        'UseLocal=1',
        'Visual=0',
        'ShutdownTerminal=1',
        f'Deposit={settings.DEPOSIT}',
        f'Currency={settings.CURRENCY}',
        f'Leverage={settings.LEVERAGE}',
    ]

    # Add parameter overrides
    if params:
        ini_lines.append('')
        ini_lines.append('[TesterInputs]')
        for name, value in params.items():
            ini_lines.append(f'{name}={value}')

    ini_content = '\n'.join(ini_lines)

    # Determine output path
    if output_path is None:
        output_path = Path(terminal['data_path']) / 'MQL5' / 'Files' / 'backtest.ini'
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(ini_content, encoding='utf-8')

    return str(output_path)


def run_backtest(
    ea_path: str,
    symbol: str,
    timeframe: str = 'H1',
    params: Optional[dict] = None,
    terminal: Optional[dict] = None,
    registry: Optional[TerminalRegistry] = None,
    timeout: int = 600,
    extract_equity: bool = True,
) -> dict:
    """
    Run a single backtest.

    Args:
        ea_path: Path to .ex5 file
        symbol: Trading symbol
        timeframe: Timeframe string (H1, M15, etc.)
        params: Parameter overrides
        terminal: Terminal config dict
        registry: TerminalRegistry instance
        timeout: Max seconds to wait for backtest
        extract_equity: If True, extract trades and compute equity curve

    Returns:
        dict with keys:
            - success: bool
            - profit: float
            - profit_factor: float
            - max_drawdown_pct: float
            - total_trades: int
            - win_rate: float
            - sharpe_ratio: float
            - sortino_ratio: float
            - expected_payoff: float
            - recovery_factor: float
            - report_path: str (path to HTML report if generated)
            - equity_curve: list[float] (if extract_equity=True)
            - errors: list
    """
    ea_path = Path(ea_path)

    if not ea_path.exists():
        return {
            'success': False,
            'errors': [f"EA file not found: {ea_path}"],
        }

    # Get terminal config
    if terminal is None:
        if registry is None:
            registry = TerminalRegistry()
        terminal = registry.get_terminal()

    # Create INI file
    ea_name = ea_path.name
    ini_path = create_backtest_ini(
        ea_name=ea_name,
        symbol=symbol,
        timeframe=timeframe,
        params=params,
        terminal=terminal,
    )

    # Run terminal with config
    terminal_exe = Path(terminal['path'])
    cmd = [str(terminal_exe), f'/config:{ini_path}']

    try:
        # Start terminal
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for completion
        start_time = time.time()
        while process.poll() is None:
            if time.time() - start_time > timeout:
                process.kill()
                return {
                    'success': False,
                    'errors': [f'Backtest timed out after {timeout} seconds'],
                }
            time.sleep(1)

    except Exception as e:
        return {
            'success': False,
            'errors': [f'Failed to run backtest: {str(e)}'],
        }

    # Parse results from report
    # MT5 generates report in terminal data_path root folder
    report_dir = Path(terminal['data_path'])

    # Find most recent report
    report_path = None
    xml_path = None

    for f in sorted(report_dir.glob('*.xml'), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.stat().st_mtime > start_time:
            xml_path = f
            break

    for f in sorted(report_dir.glob('*.htm*'), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.stat().st_mtime > start_time:
            report_path = f
            break

    # Parse results - prefer XML, fall back to HTML
    if xml_path:
        results = parse_backtest_results(xml_path)
    elif report_path:
        results = parse_html_report(Path(report_path))
    else:
        results = {'success': False, 'errors': ['No backtest results found']}

    results['report_path'] = str(report_path) if report_path else None
    results['xml_path'] = str(xml_path) if xml_path else None

    # Extract equity curve from HTML report
    if extract_equity and report_path and results.get('success'):
        try:
            from modules.trade_extractor import extract_trades, compute_equity_curve
            trades_result = extract_trades(str(report_path))
            if trades_result.success and trades_result.trades:
                equity = compute_equity_curve(trades_result.trades, trades_result.initial_balance)
                results['equity_curve'] = equity
                results['trade_count'] = len(trades_result.trades)
            else:
                results['equity_curve'] = []
        except Exception as e:
            results['equity_curve'] = []
            if 'errors' not in results:
                results['errors'] = []
            results['errors'].append(f'Equity extraction failed: {str(e)}')
    else:
        results['equity_curve'] = []

    return results


def parse_backtest_results(xml_path: Optional[Path]) -> dict:
    """Parse backtest results from XML report."""
    if xml_path is None or not Path(xml_path).exists():
        return {'success': False, 'errors': ['XML report not found']}

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Extract statistics
        stats = {}
        for stat in root.findall('.//Stat'):
            name = stat.get('name', '')
            value = stat.text or '0'
            try:
                stats[name] = float(value)
            except:
                stats[name] = value

        # Map to our standard fields
        return {
            'success': True,
            'profit': stats.get('Profit', 0),
            'profit_factor': stats.get('Profit Factor', 0),
            'max_drawdown_pct': stats.get('Equity Drawdown Maximal %',
                                stats.get('Balance Drawdown Maximal %', 0)),
            'total_trades': int(stats.get('Total Trades', 0)),
            'win_rate': stats.get('Win Rate %',
                        stats.get('Profit Trades (% of total)', 0)),
            'sharpe_ratio': stats.get('Sharpe Ratio', 0),
            'sortino_ratio': stats.get('Sortino Ratio', 0),
            'expected_payoff': stats.get('Expected Payoff', 0),
            'recovery_factor': stats.get('Recovery Factor', 0),
            'calmar_ratio': stats.get('Calmar Ratio', 0),
            'gross_profit': stats.get('Gross Profit', 0),
            'gross_loss': stats.get('Gross Loss', 0),
            'max_drawdown': stats.get('Equity Drawdown Maximal',
                            stats.get('Balance Drawdown Maximal', 0)),
            'errors': [],
        }

    except ET.ParseError as e:
        return {'success': False, 'errors': [f'Failed to parse XML: {str(e)}']}
    except Exception as e:
        return {'success': False, 'errors': [f'Error reading results: {str(e)}']}


def parse_html_report(html_path: Path) -> dict:
    """Parse backtest results from MT5 HTML report."""
    import re

    if not html_path.exists():
        return {'success': False, 'errors': ['HTML report not found']}

    try:
        # MT5 HTML reports are UTF-16-LE encoded
        with open(html_path, 'r', encoding='utf-16-le', errors='ignore') as f:
            content = f.read()
    except:
        try:
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            return {'success': False, 'errors': [f'Failed to read HTML: {str(e)}']}

    def extract_value(pattern, default=0):
        """Extract numeric value from HTML pattern."""
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            value_str = match.group(1).replace(' ', '').replace(',', '')
            try:
                return float(value_str)
            except:
                return default
        return default

    def extract_pct(pattern, default=0):
        """Extract percentage value from HTML pattern."""
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            value_str = match.group(1).replace(' ', '').replace(',', '')
            try:
                return float(value_str)
            except:
                return default
        return default

    # Extract key metrics
    profit = extract_value(r'Total Net Profit:.*?<b>([-\d., ]+)</b>')
    profit_factor = extract_value(r'Profit Factor:.*?<b>([\d.,]+)</b>')
    total_trades = int(extract_value(r'Total Trades:.*?<b>(\d+)</b>'))
    expected_payoff = extract_value(r'Expected Payoff:.*?<b>([-\d.,]+)</b>')
    sharpe_ratio = extract_value(r'Sharpe Ratio:.*?<b>([-\d.,]+)</b>')
    recovery_factor = extract_value(r'Recovery Factor:.*?<b>([-\d.,]+)</b>')
    gross_profit = extract_value(r'Gross Profit:.*?<b>([\d., ]+)</b>')
    gross_loss = extract_value(r'Gross Loss:.*?<b>([-\d., ]+)</b>')

    # Extract drawdown - format is "1 008.20 (9.87%)"
    dd_match = re.search(r'Balance Drawdown Maximal:.*?<b>([\d., ]+)\s*\(([\d.,]+)%\)', content, re.DOTALL)
    if dd_match:
        max_drawdown = float(dd_match.group(1).replace(' ', '').replace(',', ''))
        max_drawdown_pct = float(dd_match.group(2).replace(',', '.'))
    else:
        max_drawdown = 0
        max_drawdown_pct = 0

    # Extract win rate from "Short Trades (won %): 90 (51.11%)"
    win_match = re.search(r'Short Trades \(won %\):.*?<b>\d+\s*\(([\d.,]+)%\)', content)
    win_rate = float(win_match.group(1).replace(',', '.')) if win_match else 0

    return {
        'success': True,
        'profit': profit,
        'profit_factor': profit_factor,
        'max_drawdown_pct': max_drawdown_pct,
        'max_drawdown': max_drawdown,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': 0,  # Not in standard MT5 report
        'expected_payoff': expected_payoff,
        'recovery_factor': recovery_factor,
        'calmar_ratio': 0,  # Not in standard MT5 report
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'errors': [],
    }


def check_minimum_trades(results: dict) -> dict:
    """
    Check if backtest has minimum required trades.

    Returns dict with:
        - passed: bool
        - total_trades: int
        - minimum_required: int
        - message: str
    """
    trades = results.get('total_trades', 0)
    minimum = settings.MIN_TRADES

    passed = trades >= minimum

    return {
        'passed': passed,
        'total_trades': trades,
        'minimum_required': minimum,
        'message': f"{'PASS' if passed else 'FAIL'}: {trades} trades (minimum: {minimum})",
    }
