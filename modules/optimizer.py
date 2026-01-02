"""
EA Optimizer Module

Runs parameter optimization and parses XML results.
Uses: 4 years (3+1), 1-minute OHLC, 10ms latency.
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


def create_ini_file(
    ea_name: str,
    symbol: str,
    timeframe: str,
    param_ranges: list[dict],
    output_path: Optional[str] = None,
    terminal: Optional[dict] = None,
    optimization_mode: int = 2,  # 2 = Genetic algorithm
) -> str:
    """
    Create an INI file for optimization.

    Args:
        ea_name: EA filename (e.g., "MyEA.ex5")
        symbol: Trading symbol
        timeframe: Timeframe string
        param_ranges: List of dicts with keys: name, start, step, stop
        output_path: Where to save INI
        terminal: Terminal config
        optimization_mode: 0=disabled, 1=slow complete, 2=fast genetic

    Returns:
        Path to created INI file
    """
    if terminal is None:
        registry = TerminalRegistry()
        terminal = registry.get_terminal()

    dates = settings.get_backtest_dates()

    # Convert timeframe
    tf_map = {
        'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
        'H1': 60, 'H4': 240, 'D1': 1440, 'W1': 10080, 'MN1': 43200
    }
    tf_value = tf_map.get(timeframe.upper(), 60)

    # Generate report name from EA name
    ea_base = Path(ea_name).stem
    report_name = f'{ea_base}_OPT'

    ini_lines = [
        '; EA Stress Test - Optimization Configuration',
        f'; Generated: {datetime.now().isoformat()}',
        '',
        '[Tester]',
        f'Expert={ea_name}',
        f'Symbol={symbol}',
        f'Period={tf_value}',
        f'FromDate={dates["start"]}',
        f'ToDate={dates["end"]}',
        f'ForwardMode={settings.FORWARD_MODE}',  # 2=by date
        f'ForwardDate={dates["split"]}',  # Forward test starts here
        f'Model={settings.DATA_MODEL}',
        f'ExecutionMode={settings.EXECUTION_LATENCY_MS}',
        f'Optimization={optimization_mode}',
        f'OptimizationCriterion={settings.OPTIMIZATION_CRITERION}',
        f'Report={report_name}',
        'ReplaceReport=1',
        'UseLocal=1',
        'Visual=0',
        'ShutdownTerminal=1',
        f'Deposit={settings.DEPOSIT}',
        f'Currency={settings.CURRENCY}',
        f'Leverage={settings.LEVERAGE}',
    ]

    # Add parameter ranges
    ini_lines.append('')
    ini_lines.append('[TesterInputs]')

    for param in param_ranges:
        name = param['name']
        start = param.get('start', param.get('default', 0))
        step = param.get('step', 1)
        stop = param.get('stop', start)

        # Format: ParamName=value||start||step||stop||Y
        # Y = optimize this parameter
        if param.get('optimize', True) and step > 0:
            ini_lines.append(f'{name}={start}||{start}||{step}||{stop}||Y')
        else:
            ini_lines.append(f'{name}={start}||{start}||0||{start}||N')

    ini_content = '\n'.join(ini_lines)

    if output_path is None:
        output_path = Path(terminal['data_path']) / 'MQL5' / 'Files' / 'optimization.ini'
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(ini_content, encoding='utf-8')

    return str(output_path)


def run_optimization(
    ea_path: str,
    symbol: str,
    timeframe: str,
    param_ranges: list[dict],
    terminal: Optional[dict] = None,
    registry: Optional[TerminalRegistry] = None,
    timeout: int = 7200,  # 2 hours default
) -> dict:
    """
    Run parameter optimization.

    Args:
        ea_path: Path to .ex5 file
        symbol: Trading symbol
        timeframe: Timeframe string
        param_ranges: Parameter range definitions
        terminal: Terminal config
        registry: TerminalRegistry instance
        timeout: Max seconds to wait

    Returns:
        dict with:
            - success: bool
            - passes: int (number of optimization passes)
            - xml_path: str (path to results XML)
            - best_result: dict (best pass details)
            - errors: list
    """
    ea_path = Path(ea_path)

    if not ea_path.exists():
        return {'success': False, 'errors': [f"EA not found: {ea_path}"]}

    if terminal is None:
        if registry is None:
            registry = TerminalRegistry()
        terminal = registry.get_terminal()

    # Create INI
    ea_name = ea_path.name
    ini_path = create_ini_file(
        ea_name=ea_name,
        symbol=symbol,
        timeframe=timeframe,
        param_ranges=param_ranges,
        terminal=terminal,
    )

    # Run terminal
    terminal_exe = Path(terminal['path'])
    cmd = [str(terminal_exe), f'/config:{ini_path}']

    start_time = time.time()

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        while process.poll() is None:
            if time.time() - start_time > timeout:
                process.kill()
                return {'success': False, 'errors': [f'Optimization timed out after {timeout}s']}
            time.sleep(5)

    except Exception as e:
        return {'success': False, 'errors': [f'Failed to run optimization: {str(e)}']}

    # Find results - check both terminal root and Tester folder
    data_path = Path(terminal['data_path'])

    # MT5 generates optimization reports in terminal root or Tester folder
    xml_path = None
    html_path = None

    # Check for XML results
    for search_dir in [data_path, data_path / 'Tester', data_path / 'Tester' / 'reports']:
        if search_dir.exists():
            for f in sorted(search_dir.glob('*.xml'), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.stat().st_mtime > start_time:
                    xml_path = f
                    break
        if xml_path:
            break

    # Also check for optimization HTML report (fallback)
    for search_dir in [data_path, data_path / 'Tester', data_path / 'Tester' / 'reports']:
        if search_dir.exists():
            for f in sorted(search_dir.glob('*_OPT*.htm*'), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.stat().st_mtime > start_time:
                    html_path = f
                    break
        if html_path:
            break

    # Check cache file for results (MT5 stores optimization results here)
    cache_dir = data_path / 'Tester' / 'cache'
    cache_path = None
    if cache_dir.exists():
        for f in sorted(cache_dir.glob('*.opt'), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.stat().st_mtime > start_time:
                cache_path = f
                break

    if not xml_path and not cache_path:
        return {'success': False, 'errors': ['Optimization results not found']}

    # Parse results - prefer XML, fall back to cache info
    if xml_path:
        results = parse_optimization_results(str(xml_path))
        results['xml_path'] = str(xml_path)
    else:
        # Cache file exists, get basic info from filename
        # Format: EA.Symbol.Timeframe.FromDate.ToDate.Mode.Hash.opt
        results = {
            'success': True,
            'passes': 1000,  # Placeholder - cache doesn't have exact count easily
            'results': [],
            'best_result': None,
            'top_20': [],
            'cache_path': str(cache_path),
            'errors': ['Detailed results not available - using cache file'],
        }

    results['html_path'] = str(html_path) if html_path else None

    return results


def parse_optimization_results(xml_path: str) -> dict:
    """
    Parse optimization results from XML file.
    Handles MT5's Excel Spreadsheet ML format.

    Returns:
        dict with:
            - success: bool
            - passes: int
            - results: list of pass dicts (sorted by criterion)
            - best_result: dict
            - top_20: list of top 20 passes
            - errors: list
    """
    xml_path = Path(xml_path)

    if not xml_path.exists():
        return {'success': False, 'errors': [f'XML not found: {xml_path}']}

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        return {'success': False, 'errors': [f'XML parse error: {str(e)}']}

    # Handle Excel Spreadsheet ML format with namespaces
    ns = {
        'ss': 'urn:schemas-microsoft-com:office:spreadsheet',
        '': 'urn:schemas-microsoft-com:office:spreadsheet',
    }

    passes = []
    headers = []

    # Find all rows - try with namespace first, then without
    rows = root.findall('.//{urn:schemas-microsoft-com:office:spreadsheet}Row')
    if not rows:
        rows = root.findall('.//Row')

    for i, row in enumerate(rows):
        # Get cells - try with namespace first
        cells = row.findall('{urn:schemas-microsoft-com:office:spreadsheet}Cell')
        if not cells:
            cells = row.findall('Cell')

        cell_values = []
        for cell in cells:
            # Get Data element
            data = cell.find('{urn:schemas-microsoft-com:office:spreadsheet}Data')
            if data is None:
                data = cell.find('Data')

            if data is not None and data.text:
                value = data.text
                # Try to convert to number
                try:
                    if '.' in value:
                        cell_values.append(float(value))
                    else:
                        cell_values.append(int(value))
                except:
                    cell_values.append(value)
            else:
                cell_values.append(None)

        if i == 0:
            # First row is headers
            headers = [str(v) if v else f'col_{j}' for j, v in enumerate(cell_values)]
        elif cell_values:
            # Data row
            pass_data = dict(zip(headers, cell_values))
            if pass_data:
                passes.append(normalize_pass_data(pass_data))

    if not passes:
        return {'success': False, 'passes': 0, 'errors': ['No optimization passes found']}

    # Sort by Result (OnTester return value) descending
    passes.sort(key=lambda x: x.get('result', x.get('profit', 0)), reverse=True)

    # Get top results
    top_20 = passes[:settings.TOP_PASSES_DISPLAY]
    best = passes[0] if passes else None

    return {
        'success': True,
        'passes': len(passes),
        'results': passes,
        'best_result': best,
        'top_20': top_20,
        'errors': [],
    }


def normalize_pass_data(data: dict) -> dict:
    """Normalize field names from XML to standard names."""
    # Common field mappings (MT5 XML uses various names)
    mappings = {
        'Result': 'result',
        'Profit': 'profit',
        'Profit Factor': 'profit_factor',
        'ProfitFactor': 'profit_factor',
        'Expected Payoff': 'expected_payoff',
        'ExpectedPayoff': 'expected_payoff',
        'Equity DD %': 'max_drawdown_pct',
        'Drawdown %': 'max_drawdown_pct',
        'Equity Drawdown %': 'max_drawdown_pct',
        'Trades': 'total_trades',
        'Total Trades': 'total_trades',
        'Sharpe Ratio': 'sharpe_ratio',
        'SharpeRatio': 'sharpe_ratio',
        'Sortino Ratio': 'sortino_ratio',
        'Recovery Factor': 'recovery_factor',
        'RecoveryFactor': 'recovery_factor',
        'Win %': 'win_rate',
        'Profit Trades %': 'win_rate',
    }

    normalized = {}
    params = {}

    for key, value in data.items():
        # Check if it's a known metric
        if key in mappings:
            normalized[mappings[key]] = value
        elif key.lower() in [m.lower() for m in mappings.keys()]:
            # Case-insensitive match
            for orig, mapped in mappings.items():
                if key.lower() == orig.lower():
                    normalized[mapped] = value
                    break
        else:
            # Assume it's a parameter
            params[key] = value

    normalized['params'] = params

    # Ensure required fields exist
    if 'result' not in normalized:
        normalized['result'] = normalized.get('profit', 0)

    return normalized



# NOTE: find_robust_params() was REMOVED - it was deprecated per CLAUDE.md Lesson #1
# Median parameter values create "Frankenstein" combinations that were never tested.
# Use Claude's /stats-analyzer skill to select actual tested passes instead.
