"""
EA Optimizer Module

Runs parameter optimization and parses XML results.
Uses: 4 years (3+1), 1-minute OHLC, 10ms latency.
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


def create_ini_file(
    ea_name: str,
    symbol: str,
    timeframe: str,
    param_ranges: list[dict],
    report_name: Optional[str] = None,
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

    # Report name (overrideable for deterministic multi-run workflows)
    ea_base = Path(ea_name).stem
    report_name = report_name or f'{ea_base}_OPT'

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

        # Handle fixed boolean parameters (e.g., {'name': 'Enable_X', 'fixed': True})
        if 'fixed' in param and isinstance(param['fixed'], bool):
            # Convert Python bool to MQL5 bool string
            val = 'true' if param['fixed'] else 'false'
            ini_lines.append(f'{name}={val}||{val}||0||{val}||N')
            continue

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
    report_name: Optional[str] = None,
    terminal: Optional[dict] = None,
    registry: Optional[TerminalRegistry] = None,
    timeout: int = 7200,  # 2 hours default
    on_progress: Optional[Callable[[str], None]] = None,
    progress_interval_s: int = 30,
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
        report_name=report_name,
        terminal=terminal,
    )

    # Run terminal
    terminal_exe = Path(terminal['path'])
    _terminate_terminal_processes(terminal_exe)
    cmd = [str(terminal_exe), f'/config:{ini_path}']

    start_time = time.time()
    last_progress = start_time

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        while process.poll() is None:
            if time.time() - start_time > timeout:
                process.kill()
                return {'success': False, 'errors': [f'Optimization timed out after {timeout}s']}
            if on_progress and (time.time() - last_progress) >= float(progress_interval_s or 30):
                try:
                    elapsed = time.time() - start_time
                    on_progress(
                        f"Optimization running: {report_name or ea_path.stem} {symbol} {timeframe} "
                        f"({elapsed:.0f}s elapsed)"
                    )
                except Exception:
                    pass
                last_progress = time.time()
            time.sleep(5)

    except Exception as e:
        return {'success': False, 'errors': [f'Failed to run optimization: {str(e)}']}

    # Find results - check terminal root and Tester folders.
    # MT5 creates multiple reports when ForwardMode is enabled:
    #   - <Report>.xml (main/back segment)
    #   - <Report>.forward.xml (forward segment)
    # We prefer the main report for primary metrics, then merge forward/back results
    # so downstream analysis can reason about both segments.
    data_path = Path(terminal['data_path'])

    # MT5 generates optimization reports in terminal root or Tester folder.
    # Prefer our expected report name over "most recent XML" to avoid accidentally
    # selecting the *.forward.xml file as the primary report.
    xml_path = None
    forward_xml_path = None
    html_path = None

    report_base = str(report_name).strip() if report_name else f"{ea_path.stem}_OPT"
    search_dirs = [data_path, data_path / 'Tester', data_path / 'Tester' / 'reports']

    def _latest(paths: list[Path]) -> Optional[Path]:
        if not paths:
            return None
        return max(paths, key=lambda x: x.stat().st_mtime)

    main_candidates: list[Path] = []
    forward_candidates: list[Path] = []

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        main_candidates.extend(search_dir.glob(f"{report_base}.xml"))
        forward_candidates.extend(search_dir.glob(f"{report_base}.forward.xml"))

    # Only consider newly-written reports from this run (timestamp skew tolerance)
    mtime_threshold = float(start_time) - 2.0
    main_candidates = [p for p in main_candidates if p.stat().st_mtime >= mtime_threshold]
    forward_candidates = [p for p in forward_candidates if p.stat().st_mtime >= mtime_threshold]

    xml_path = _latest(main_candidates)
    forward_xml_path = _latest(forward_candidates)

    # Fallback only when report_name is not specified (avoid picking the wrong EA/run)
    if not xml_path and not report_name:
        xml_candidates: list[Path] = []
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for f in sorted(search_dir.glob('*.xml'), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.stat().st_mtime < mtime_threshold:
                    continue
                if f.name.endswith('.forward.xml'):
                    continue
                xml_candidates.append(f)
        xml_path = _latest(xml_candidates)

    # Also check for optimization HTML report (deterministic when possible)
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for f in sorted(search_dir.glob(f"{report_base}.htm*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.stat().st_mtime >= mtime_threshold:
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

    if report_name and not xml_path and not cache_path:
        return {'success': False, 'errors': [f'Optimization results not found for report_name: {report_base}']}

    if not xml_path and not cache_path:
        return {'success': False, 'errors': ['Optimization results not found']}

    # Parse results - prefer XML, fall back to cache info
    if xml_path:
        results = parse_optimization_results(str(xml_path))
        results['xml_path'] = str(xml_path)

        # Merge forward segment info when available
        if forward_xml_path and forward_xml_path.exists():
            forward = parse_optimization_results(str(forward_xml_path))
            results['forward_xml_path'] = str(forward_xml_path)
            _merge_forward_results(results.get('results', []), forward.get('results', []))
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


def _merge_forward_results(base_results: list[dict], forward_results: list[dict]) -> None:
    """
    Merge MT5 forward report data into the main optimization results.

    The main report (<name>_OPT.xml) contains the back/in-sample segment.
    The forward report (<name>_OPT.forward.xml) contains the forward segment plus
    'Forward Result'/'Back Result' columns (optimization criterion values).
    """
    forward_by_pass: dict[int, dict] = {}

    for p in forward_results:
        params = p.get('params') or {}
        pass_num = params.get('Pass')
        if isinstance(pass_num, int):
            forward_by_pass[pass_num] = p

    for p in base_results:
        params = p.get('params') or {}
        pass_num = params.get('Pass')
        if not isinstance(pass_num, int):
            continue

        # Ensure 'Back Result' exists even if the forward report isn't found
        if 'Back Result' not in params:
            params['Back Result'] = p.get('result', 0)

        fwd = forward_by_pass.get(pass_num)
        if not fwd:
            continue

        fwd_params = fwd.get('params') or {}

        # Attach criterion breakdown into params for downstream analyzers
        if 'Forward Result' in fwd_params:
            params['Forward Result'] = fwd_params['Forward Result']
        if 'Back Result' in fwd_params:
            params['Back Result'] = fwd_params['Back Result']

        # Attach forward-segment metrics (use distinct keys to avoid ambiguity)
        p['forward_profit'] = fwd.get('profit', 0)
        p['forward_expected_payoff'] = fwd.get('expected_payoff', 0)
        p['forward_profit_factor'] = fwd.get('profit_factor', 0)
        p['forward_recovery_factor'] = fwd.get('recovery_factor', 0)
        p['forward_sharpe_ratio'] = fwd.get('sharpe_ratio', 0)
        p['forward_max_drawdown_pct'] = fwd.get('max_drawdown_pct', 0)
        p['forward_total_trades'] = fwd.get('total_trades', 0)

        # Trade counts are additive across segments; expose combined for convenience.
        try:
            p['total_trades'] = int(p.get('total_trades', 0) or 0) + int(fwd.get('total_trades', 0) or 0)
        except Exception:
            # Keep original if any weirdness in types
            pass


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
