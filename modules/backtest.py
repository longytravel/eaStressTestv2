"""
EA Backtest Module

Runs single backtests using MT5 terminal.
Always uses: 4 years (3+1), 1-minute OHLC, 10ms latency.
"""
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.terminals import TerminalRegistry
import settings


def _terminate_terminal_processes(terminal_exe: Path) -> None:
    """Best-effort cleanup of stuck terminal/metatester processes for this terminal install."""
    try:
        import psutil
    except Exception:
        return

    try:
        terminal_exe_resolved = str(terminal_exe.resolve()).lower()
    except Exception:
        terminal_exe_resolved = str(terminal_exe).lower()

    exe_paths = {terminal_exe_resolved}
    metatester_exe = terminal_exe.parent / 'metatester64.exe'
    if metatester_exe.exists():
        try:
            exe_paths.add(str(metatester_exe.resolve()).lower())
        except Exception:
            exe_paths.add(str(metatester_exe).lower())

    to_kill = []
    for proc in psutil.process_iter(['pid', 'exe']):
        try:
            exe = proc.info.get('exe')
            if not exe:
                continue
            exe_norm = str(Path(exe).resolve()).lower()
            if exe_norm in exe_paths:
                to_kill.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, FileNotFoundError):
            continue
        except Exception:
            continue

    for proc in to_kill:
        try:
            proc.kill()
        except Exception:
            continue

    for proc in to_kill:
        try:
            proc.wait(timeout=5)
        except Exception:
            continue


def create_backtest_ini(
    ea_name: str,
    symbol: str,
    timeframe: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    model: Optional[int] = None,
    execution_latency_ms: Optional[int] = None,
    spread: Optional[int] = None,
    report_name: Optional[str] = None,
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

    # Get dynamic dates (overrideable for scenario/tick validation runs)
    dates = settings.get_backtest_dates()
    from_date = from_date or dates["start"]
    to_date = to_date or dates["end"]
    model = settings.DATA_MODEL if model is None else model
    execution_latency_ms = settings.EXECUTION_LATENCY_MS if execution_latency_ms is None else execution_latency_ms

    # Convert timeframe to MT5 format
    tf_map = {
        'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
        'H1': 60, 'H4': 240, 'D1': 1440, 'W1': 10080, 'MN1': 43200
    }
    tf_value = tf_map.get(timeframe.upper(), 60)

    # Generate report name from EA name (overrideable for deterministic multi-run scenarios)
    ea_base = Path(ea_name).stem
    report_name = report_name or f'{ea_base}_BT'

    # Build INI content
    ini_lines = [
        '; EA Stress Test - Backtest Configuration',
        f'; Generated: {datetime.now().isoformat()}',
        '',
        '[Tester]',
        f'Expert={ea_name}',
        f'Symbol={symbol}',
        f'Period={tf_value}',
        f'FromDate={from_date}',
        f'ToDate={to_date}',
        f'Model={model}',  # 0=ticks, 1=1-minute OHLC, 2=open prices
        f'ExecutionMode={execution_latency_ms}',
        *( [f'Spread={spread}'] if spread is not None else [] ),
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
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    model: Optional[int] = None,
    execution_latency_ms: Optional[int] = None,
    spread: Optional[int] = None,
    report_name: Optional[str] = None,
    terminal: Optional[dict] = None,
    registry: Optional[TerminalRegistry] = None,
    timeout: int = 600,
    extract_equity: bool = True,
    on_progress: Optional[Callable[[str], None]] = None,
    progress_interval_s: int = 30,
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
        from_date=from_date,
        to_date=to_date,
        model=model,
        execution_latency_ms=execution_latency_ms,
        spread=spread,
        report_name=report_name,
        params=params,
        terminal=terminal,
    )

    # Run terminal with config
    terminal_exe = Path(terminal['path'])
    _terminate_terminal_processes(terminal_exe)
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
        last_progress = start_time
        while process.poll() is None:
            if time.time() - start_time > timeout:
                process.kill()
                return {
                    'success': False,
                    'errors': [f'Backtest timed out after {timeout} seconds'],
                }
            if on_progress and (time.time() - last_progress) >= float(progress_interval_s or 30):
                try:
                    elapsed = time.time() - start_time
                    on_progress(
                        f"Backtest running: {report_name or ea_path.stem} {symbol} {timeframe} "
                        f"({elapsed:.0f}s elapsed)"
                    )
                except Exception:
                    pass
                last_progress = time.time()
            time.sleep(1)

    except Exception as e:
        return {
            'success': False,
            'errors': [f'Failed to run backtest: {str(e)}'],
        }

    # Parse results from report
    # MT5 generates report in terminal data_path root folder
    report_dir = Path(terminal['data_path'])

    report_path = None
    xml_path = None

    # When report_name is provided, be deterministic: only accept that report name.
    # Using a strict "mtime > start_time" is flaky on some filesystems due to timestamp
    # resolution, and falling back to "most recent report" can silently read the wrong run.
    if report_name:
        mtime_threshold = float(start_time) - 2.0  # allow small timestamp skew

        # Give MT5 a moment to flush report files after the process exits.
        for _ in range(10):
            expected_xml = report_dir / f'{report_name}.xml'
            html_candidates = list(report_dir.glob(f'{report_name}.htm*'))
            if expected_xml.exists() or html_candidates:
                break
            time.sleep(0.5)

        expected_xml = report_dir / f'{report_name}.xml'
        if expected_xml.exists():
            try:
                if expected_xml.stat().st_mtime >= mtime_threshold:
                    xml_path = expected_xml
            except Exception:
                xml_path = expected_xml

        html_candidates = sorted(
            report_dir.glob(f'{report_name}.htm*'),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        for f in html_candidates:
            try:
                if f.stat().st_mtime >= mtime_threshold:
                    report_path = f
                    break
            except Exception:
                report_path = f
                break

        # If we found candidates but timestamps look "stale", still use the newest file.
        if report_path is None and html_candidates:
            report_path = html_candidates[0]
        if xml_path is None and expected_xml.exists():
            xml_path = expected_xml

        if report_path is None and xml_path is None:
            return {
                'success': False,
                'errors': [f'No backtest report found for report_name: {report_name}'],
                'report_path': None,
                'xml_path': None,
            }

    # Otherwise, fall back to the most recent report created after this run started.
    if report_name is None:
        for f in sorted(report_dir.glob('*.xml'), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.stat().st_mtime > start_time:
                xml_path = f
                break

        for f in sorted(report_dir.glob('*.htm*'), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.stat().st_mtime > start_time:
                report_path = f
                break

    # Parse results
    # Prefer HTML when available because it includes data-quality and extended fields (e.g., History Quality).
    results = None
    if report_path:
        results = parse_html_report(Path(report_path))
        # If HTML parsing fails but XML exists, fall back.
        if not results.get('success') and xml_path:
            results = parse_backtest_results(xml_path)
    elif xml_path:
        results = parse_backtest_results(xml_path)
    else:
        results = {'success': False, 'errors': ['No backtest results found']}

    results['report_path'] = str(report_path) if report_path else None
    results['xml_path'] = str(xml_path) if xml_path else None

    # Extract equity curve from HTML report
    if extract_equity and report_path and results.get('success'):
        try:
            from modules.trade_extractor import (
                extract_trades,
                compute_equity_curve,
                generate_chart_data,
                split_trades_by_date,
            )
            trades_result = extract_trades(str(report_path))
            if trades_result.success and trades_result.trades:
                equity = compute_equity_curve(trades_result.trades, trades_result.initial_balance)
                results['equity_curve'] = equity
                results['trade_count'] = len(trades_result.trades)
                results['charts'] = generate_chart_data(trades_result.trades)

                # Prefer totals computed directly from the deal list
                results['costs'] = {
                    'total_commission': trades_result.total_commission,
                    'total_swap': trades_result.total_swap,
                }

                # Split in-sample vs forward based on the global workflow split date
                try:
                    split_str = settings.get_backtest_dates().get('split')
                    split_dt = datetime.strptime(split_str, "%Y.%m.%d") if split_str else None
                except Exception:
                    split_str = None
                    split_dt = None

                if split_dt:
                    before_trades, after_trades = split_trades_by_date(trades_result.trades, split_dt)

                    in_sample_equity = compute_equity_curve(before_trades, trades_result.initial_balance)
                    forward_start_balance = (
                        in_sample_equity[-1] if in_sample_equity else trades_result.initial_balance
                    )
                    forward_equity = compute_equity_curve(after_trades, forward_start_balance)

                    results['equity_curve_in_sample'] = in_sample_equity
                    results['equity_curve_forward'] = forward_equity

                    results['split_date'] = split_str
                    results['split_profit_in_sample'] = sum(t.net_profit for t in before_trades)
                    results['split_profit_forward'] = sum(t.net_profit for t in after_trades)
                    results['split_trades_in_sample'] = len(before_trades)
                    results['split_trades_forward'] = len(after_trades)
                else:
                    # No split available; treat as all in-sample
                    results['equity_curve_in_sample'] = equity
                    results['equity_curve_forward'] = []
                    results['split_date'] = None
                    results['split_profit_in_sample'] = sum(t.net_profit for t in trades_result.trades)
                    results['split_profit_forward'] = 0.0
                    results['split_trades_in_sample'] = len(trades_result.trades)
                    results['split_trades_forward'] = 0
            else:
                results['equity_curve'] = []
                results['equity_curve_in_sample'] = []
                results['equity_curve_forward'] = []
                results['charts'] = {}
                results['split_date'] = None
                results['split_profit_in_sample'] = 0.0
                results['split_profit_forward'] = 0.0
                results['split_trades_in_sample'] = 0
                results['split_trades_forward'] = 0
        except Exception as e:
            results['equity_curve'] = []
            results['equity_curve_in_sample'] = []
            results['equity_curve_forward'] = []
            results['charts'] = {}
            results['split_date'] = None
            results['split_profit_in_sample'] = 0.0
            results['split_profit_forward'] = 0.0
            results['split_trades_in_sample'] = 0
            results['split_trades_forward'] = 0
            if 'errors' not in results:
                results['errors'] = []
            results['errors'].append(f'Equity extraction failed: {str(e)}')
    else:
        results['equity_curve'] = []
        results['equity_curve_in_sample'] = []
        results['equity_curve_forward'] = []
        results['charts'] = {}
        results['split_date'] = None
        results['split_profit_in_sample'] = 0.0
        results['split_profit_forward'] = 0.0
        results['split_trades_in_sample'] = 0
        results['split_trades_forward'] = 0

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
    """Parse backtest results from MT5 HTML report with extended metrics.

    MT5 HTML format uses tables:
    <td>Label:</td><td><b>VALUE</b></td>
    """
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

    found_labels = set()

    def clean_num(s):
        """Parse MT5 numeric strings.

        MT5 commonly uses spaces as thousands separators. Some locales use comma decimals.
        """
        if not s:
            return 0
        s = str(s).strip()
        s = s.replace('\xa0', '').replace('%', '').replace(' ', '')

        # Locale-aware decimal/thousands handling:
        # - If both ',' and '.' are present: assume ',' is thousands separator.
        # - If only ',' is present: assume it's a decimal separator.
        if ',' in s and '.' in s:
            s = s.replace(',', '')
        elif ',' in s and '.' not in s:
            s = s.replace(',', '.')

        # Strip any remaining thousands separators (apostrophes) or stray chars
        s = s.replace("'", '')

        try:
            return float(s)
        except Exception:
            return 0

    def extract_value(label, default=0):
        """Extract numeric value after a label in MT5 HTML table format.

        MT5 format: >Label:</td>...<td...><b>VALUE</b></td>
        """
        # Escape special regex chars in label but allow flexible whitespace
        escaped = re.escape(label).replace(r'\ ', r'\s*')
        pattern = rf'>{escaped}:?</td>.*?<b>([^<]+)</b>'
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            found_labels.add(label)
            val_str = match.group(1).strip()
            # Handle "VALUE (PCT%)" format - take just the value part
            if '(' in val_str:
                val_str = val_str.split('(')[0].strip()
            return clean_num(val_str)
        return default

    def extract_value_pct(label, default_val=0, default_pct=0):
        """Extract value and percentage from format like '2 656.13 (82.77%)'"""
        escaped = re.escape(label).replace(r'\ ', r'\s*')
        pattern = rf'>{escaped}:?</td>.*?<b>([^<]+)</b>'
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            found_labels.add(label)
            text = match.group(1).strip()
            # Parse "VALUE (PCT%)" format
            pct_match = re.search(r'([\d\s.,\-]+)\s*\(([\d.,]+)%\)', text)
            if pct_match:
                val = clean_num(pct_match.group(1))
                pct = float(pct_match.group(2).replace(',', '.'))
                return val, pct
            # Just value, no percentage
            return clean_num(text), default_pct
        return default_val, default_pct

    def extract_count_pct(label, default_count=0, default_pct=0):
        """Extract count and win % from format like '543 (48.43%)'"""
        escaped = re.escape(label).replace(r'\ ', r'\s*')
        pattern = rf'>{escaped}:?</td>.*?<b>([^<]+)</b>'
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            found_labels.add(label)
            text = match.group(1).strip()
            # Parse "COUNT (PCT%)" format
            pct_match = re.search(r'(\d+)\s*\(([\d.,]+)%\)', text)
            if pct_match:
                count = int(pct_match.group(1))
                pct = float(pct_match.group(2).replace(',', '.'))
                return count, pct
        return default_count, default_pct

    def extract_streak(label, default_count=0, default_amount=0):
        """Extract streak from format like '10 (112.55)' for wins or '275.28 (3)' for profit."""
        # If label contains regex patterns (backslashes), don't escape it further
        if '\\' in label:
            escaped = label.replace(r'\ ', r'\s*')
        else:
            escaped = re.escape(label).replace(r'\ ', r'\s*')
        pattern = rf'>{escaped}:?</td>.*?<b>([^<]+)</b>'
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            found_labels.add(label)
            text = match.group(1).strip()
            # Format: "COUNT (AMOUNT)" or "AMOUNT (COUNT)"
            parts_match = re.search(r'([\d\s.,\-]+)\s*\(([\d\s.,\-]+)\)', text)
            if parts_match:
                p1 = clean_num(parts_match.group(1))
                p2 = clean_num(parts_match.group(2))
                # If "wins" in label, format is COUNT (AMOUNT)
                if 'wins' in label.lower() or 'losses' in label.lower():
                    return int(p1), p2
                # If "profit" or "loss" in label, format is AMOUNT (COUNT)
                return int(p2), p1
        return default_count, default_amount

    def extract_text(label, default=''):
        """Extract text value after a label."""
        escaped = re.escape(label).replace(r'\ ', r'\s*')
        pattern = rf'>{escaped}:?</td>.*?<b>([^<]+)</b>'
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        if match:
            found_labels.add(label)
            return match.group(1).strip()
        return default

    # === Core Metrics ===
    # Data quality (from "Results" header row)
    history_quality_pct = extract_value('History Quality')
    bars = int(extract_value('Bars'))
    ticks = int(extract_value('Ticks'))
    symbols = int(extract_value('Symbols'))

    profit = extract_value('Total Net Profit')
    profit_factor = extract_value('Profit Factor')
    total_trades = int(extract_value('Total Trades'))
    expected_payoff = extract_value('Expected Payoff')
    sharpe_ratio = extract_value('Sharpe Ratio')
    recovery_factor = extract_value('Recovery Factor')
    gross_profit = extract_value('Gross Profit')
    gross_loss = extract_value('Gross Loss')

    # === Statistical Metrics ===
    # Z-Score format: "-1.65 (90.11%)"
    z_score, z_score_confidence = extract_value_pct('Z-Score')

    # === Returns (AHPR/GHPR) ===
    # Format: "0.9986 (-0.14%)"
    ahpr = extract_value('AHPR')
    ghpr = extract_value('GHPR')

    # === Linear Regression Metrics ===
    lr_correlation = extract_value('LR Correlation')
    lr_standard_error = extract_value('LR Standard Error')

    # === Drawdown ===
    balance_dd_abs = extract_value('Balance Drawdown Absolute')
    balance_dd_max, balance_dd_rel = extract_value_pct('Balance Drawdown Maximal')
    equity_dd_abs = extract_value('Equity Drawdown Absolute')
    equity_dd_max, equity_dd_rel = extract_value_pct('Equity Drawdown Maximal')

    # Use equity DD as max_drawdown_pct if available, else balance
    max_drawdown_pct = equity_dd_rel if equity_dd_rel > 0 else balance_dd_rel
    max_drawdown = equity_dd_max if equity_dd_max > 0 else balance_dd_max

    # === Win/Loss Streaks ===
    # MT5 format: "Maximum consecutive wins ($):" -> "10 (112.55)"
    max_consecutive_wins, max_consec_win_amount = extract_streak(r'Maximum consecutive wins \(\$\)')
    max_consecutive_losses, max_consec_loss_amount = extract_streak(r'Maximum consecutive losses \(\$\)')
    # "Maximal consecutive profit (count):" -> "275.28 (3)"
    max_consec_profit_count, max_consecutive_profit = extract_streak(r'Maximal consecutive profit \(count\)')
    max_consec_loss_count, max_consecutive_loss = extract_streak(r'Maximal consecutive loss \(count\)')

    # Average consecutive
    avg_consecutive_wins = int(extract_value('Average consecutive wins'))
    avg_consecutive_losses = int(extract_value('Average consecutive losses'))

    # === Trade Size Metrics ===
    largest_profit_trade = extract_value('Largest profit trade')
    largest_loss_trade = extract_value('Largest loss trade')
    avg_profit_trade = extract_value('Average profit trade')
    avg_loss_trade = extract_value('Average loss trade')

    # === Holding Time ===
    # MT5 uses "Minimal/Maximal" not "Minimum/Maximum"
    min_holding_time = extract_text('Minimal position holding time')
    max_holding_time = extract_text('Maximal position holding time')
    avg_holding_time = extract_text('Average position holding time')

    # === Costs ===
    total_commission = extract_value('Total commission')
    total_swap = extract_value('Total swap')

    # === Direction (Long/Short) ===
    # "Short Trades (won %):" -> "543 (48.43%)"
    short_trades, short_win_pct = extract_count_pct('Short Trades (won %)')
    long_trades, long_win_pct = extract_count_pct('Long Trades (won %)')

    # Calculate overall win rate from long/short
    if short_trades + long_trades > 0:
        win_rate = (short_win_pct * short_trades + long_win_pct * long_trades) / (short_trades + long_trades)
    else:
        win_rate = 0

    # Profit/loss trades count - "Profit Trades (% of total):" -> "544 (49.19%)"
    profit_trades, _ = extract_count_pct('Profit Trades (% of total)')
    loss_trades, _ = extract_count_pct('Loss Trades (% of total)')

    # Basic parse validation: if we couldn't match core labels, the report format likely differs.
    required = {'Total Net Profit', 'Total Trades', 'Profit Factor', 'Equity Drawdown Maximal', 'History Quality'}
    matched_core = len(required.intersection(found_labels))
    parse_errors = []
    if matched_core < 2:
        parse_errors.append(
            f"Failed to match core fields in MT5 HTML report (matched {matched_core}/"
            f"{len(required)}); report format may have changed."
        )

    return {
        'success': matched_core >= 2,
        # Data quality
        'history_quality_pct': history_quality_pct,
        'bars': bars,
        'ticks': ticks,
        'symbols': symbols,
        # Core metrics
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

        # Extended: Statistical
        'z_score': z_score,
        'z_score_confidence': z_score_confidence,

        # Extended: Returns
        'ahpr': ahpr,
        'ghpr': ghpr,

        # Extended: Linear Regression
        'lr_correlation': lr_correlation,
        'lr_standard_error': lr_standard_error,

        # Extended: Drawdown details
        'drawdown': {
            'balance_dd_abs': balance_dd_abs,
            'balance_dd_max': balance_dd_max,
            'balance_dd_rel': balance_dd_rel,
            'equity_dd_abs': equity_dd_abs,
            'equity_dd_max': equity_dd_max,
            'equity_dd_rel': equity_dd_rel,
        },

        # Extended: Streaks
        'streaks': {
            'max_consecutive_wins': max_consecutive_wins,
            'max_consecutive_losses': max_consecutive_losses,
            'max_consecutive_profit': max_consecutive_profit,
            'max_consecutive_loss': max_consecutive_loss,
            'avg_consecutive_wins': avg_consecutive_wins,
            'avg_consecutive_losses': avg_consecutive_losses,
        },

        # Extended: Trade sizes
        'positions': {
            'largest_profit_trade': largest_profit_trade,
            'largest_loss_trade': largest_loss_trade,
            'avg_profit_trade': avg_profit_trade,
            'avg_loss_trade': avg_loss_trade,
            'profit_trades': profit_trades,
            'loss_trades': loss_trades,
        },

        # Extended: Holding times
        'holding_times': {
            'min_holding_time': min_holding_time,
            'max_holding_time': max_holding_time,
            'avg_holding_time': avg_holding_time,
        },

        # Extended: Costs
        'costs': {
            'total_commission': total_commission,
            'total_swap': total_swap,
        },

        # Extended: Direction
        'direction': {
            'short_trades': short_trades,
            'short_win_pct': short_win_pct,
            'long_trades': long_trades,
            'long_win_pct': long_win_pct,
        },

        'errors': parse_errors,
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
