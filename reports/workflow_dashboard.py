"""
Generate interactive dashboard from workflow state JSON.

Uses SPA (Single Page Application) approach with JSON-embedded data.
Supports running backtests for top passes to get full equity curves.
"""
import json
import sys
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

# Direct import to avoid circular dependency through modules/__init__.py
from modules.loader import load_module

_pass_analyzer = load_module("pass_analyzer", "modules/pass_analyzer.py")
analyze_passes = _pass_analyzer.analyze_passes


def generate_dashboard_from_workflow(
    workflow_path: str,
    output_dir: Optional[str] = None,
    open_browser: bool = False,
    run_backtests: bool = False,
    top_n: int = 20,
) -> str:
    """
    Generate interactive dashboard from workflow state JSON file.

    Args:
        workflow_path: Path to workflow JSON file
        output_dir: Output directory (default: runs/dashboards/{workflow_id})
        open_browser: Open in browser after generation
        run_backtests: Whether to run backtests for top passes (slow but gets equity curves)
        top_n: Number of top passes to backtest

    Returns:
        Path to generated dashboard
    """
    with open(workflow_path, 'r') as f:
        state = json.load(f)

    # Determine workflow ID
    workflow_id = state.get('workflow_id', '')
    if not workflow_id:
        workflow_id = Path(workflow_path).stem

    # Prepare dashboard data
    if run_backtests:
        # Run backtests for top passes to get equity curves
        from reports.pass_backtest import backtest_top_passes, prepare_dashboard_data
        pass_results = backtest_top_passes(state, top_n=top_n)
        data = prepare_dashboard_data(state, pass_results)
    else:
        # Use optimization data only (fast but no per-trade equity)
        data = prepare_data_from_optimization(state)

    # Determine output directory
    if output_dir is None:
        output_dir = Path('runs/dashboards') / workflow_id
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Read SPA template
    templates_dir = Path(__file__).parent / 'templates'
    template_path = templates_dir / 'dashboard_spa.html'

    if not template_path.exists():
        raise FileNotFoundError(f"Dashboard template not found: {template_path}")

    template = template_path.read_text(encoding='utf-8')

    # Embed JSON data
    json_data = json.dumps(data, indent=2)
    html = template.replace('{{DATA_JSON}}', json_data)
    html = html.replace('{{ea_name}}', data.get('ea_name', 'EA Dashboard'))

    # Write output
    output_path = output_dir / 'index.html'
    output_path.write_text(html, encoding='utf-8')

    # Also save raw data for debugging/API access
    data_path = output_dir / 'data.json'
    data_path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    if open_browser:
        import webbrowser
        webbrowser.open(f'file://{output_path.absolute()}')

    return str(output_path)


def prepare_data_from_optimization(state: dict) -> dict:
    """
    Prepare dashboard data from workflow state.

    Prefers step 9 backtest results when available (more accurate),
    falls back to step 7 optimization results.
    """
    # Basic info
    ea_name = state.get('ea_name', 'Unknown')
    symbol = state.get('symbol', 'EURUSD')
    timeframe = state.get('timeframe', 'H1')

    backtest_dates = state.get('backtest_dates', {})
    from_date = backtest_dates.get('start', '')
    to_date = backtest_dates.get('end', '')
    forward_date = backtest_dates.get('split', '')

    steps = state.get('steps', {})

    # Check for step 9 backtest results first (preferred - more accurate)
    bt_step = steps.get('9_backtest_robust', {})
    bt_result = bt_step.get('result', {})
    backtest_results = bt_result.get('all_results', [])

    if backtest_results:
        # Use actual backtest results
        return _prepare_data_from_backtests(state, backtest_results)

    # Fall back to optimization results
    opt_step = steps.get('7_run_optimization', {})
    opt_result = opt_step.get('result', {})
    all_results = opt_result.get('results', [])

    # Analyze passes
    if all_results:
        analysis = analyze_passes(all_results)
    else:
        analysis = {
            'total_passes': 0,
            'valid_count': 0,
            'consistent_count': 0,
            'filtered_passes': [],
            'rejected_passes': {},
            'insights': ['No optimization results available'],
        }

    # Build scatter data
    scatter_data = []
    for p in analysis.get('filtered_passes', []):
        scatter_data.append({
            'x': p.get('back_result', 0),
            'y': p.get('forward_result', 0),
        })

    # Build pass data from optimization (simplified - no equity curves)
    pass_list = []
    passes_data = {}

    for p in analysis.get('filtered_passes', [])[:50]:  # Top 50
        params = p.get('params', {})
        pass_number = params.get('Pass', 0)
        pass_list.append(pass_number)

        # Filter params to remove metadata
        skip_params = {'Pass', 'Forward Result', 'Back Result', 'Custom', 'Result'}
        clean_params = {k: v for k, v in params.items() if k not in skip_params}

        passes_data[str(pass_number)] = {
            'success': True,
            'pass': pass_number,
            'parameters': clean_params,
            'opt': {
                'in_profit': p.get('back_result', 0),
                'fwd_profit': p.get('forward_result', 0),
            },
            'bt': {
                'total_trades': p.get('total_trades', 0),
                'net_profit': p.get('profit', 0),
                'profit_factor': p.get('profit_factor', 0),
                'max_drawdown_pct': p.get('max_drawdown_pct', 0),
                'sharpe_ratio': p.get('sharpe_ratio', 0),
                'recovery_factor': p.get('recovery_factor', 0),
                'win_rate': 0,  # Not available from optimization
                'split': {
                    'in_sample': {'net_profit': 0, 'trades': 0},
                    'forward': {'net_profit': 0, 'trades': 0}
                }
            },
            'equity': {
                'in_sample': [],  # Not available without backtest
                'forward': []
            },
            'monte_carlo': {
                'confidence': 0,
                'ruin_probability': 0,
                'median_profit': 0,
                'worst_5pct': 0,
                'best_95pct': 0,
            }
        }

    # Claude analysis
    claude_analysis = state.get('claude_analysis', '')

    # Gate results
    gates = state.get('gates', {})

    return {
        'ea_name': ea_name,
        'symbol': symbol,
        'timeframe': timeframe,
        'from_date': from_date,
        'to_date': to_date,
        'forward_date': forward_date,
        'optimization': {
            'total_passes': analysis.get('total_passes', 0),
            'valid_passes': analysis.get('valid_count', 0),
            'consistent_passes': analysis.get('consistent_count', 0),
            'rejected': analysis.get('rejected_passes', {}),
            'scatter': scatter_data,
            'insights': analysis.get('insights', []),
        },
        'pass_list': pass_list,
        'passes': passes_data,
        'selected_pass': pass_list[0] if pass_list else None,
        'claude_analysis': claude_analysis,
        'gates': gates,
        'thresholds': {
            'min_trades': 50,
            'min_profit_factor': 1.5,
            'max_drawdown_pct': 30.0,
            'min_mc_confidence': 70,
            'max_ruin_probability': 5,
        }
    }


def _prepare_data_from_backtests(state: dict, backtest_results: list) -> dict:
    """Prepare dashboard data from step 9 backtest results (preferred, more accurate)."""

    ea_name = state.get('ea_name', 'Unknown')
    symbol = state.get('symbol', 'EURUSD')
    timeframe = state.get('timeframe', 'H1')

    backtest_dates = state.get('backtest_dates', {})
    from_date = backtest_dates.get('start', '')
    to_date = backtest_dates.get('end', '')
    forward_date = backtest_dates.get('split', '')

    # Sort by profit descending
    sorted_results = sorted(backtest_results, key=lambda x: x.get('profit', 0), reverse=True)

    # Build scatter data
    scatter_data = []
    for p in sorted_results:
        scatter_data.append({
            'x': p.get('back_result', 0),
            'y': p.get('forward_result', 0),
        })

    # Build pass data
    pass_list = []
    passes_data = {}

    for p in sorted_results[:50]:
        pass_num = p.get('pass_num', 0)
        pass_list.append(pass_num)

        profit = p.get('profit', 0)
        pf = p.get('profit_factor', 0)
        dd = p.get('max_drawdown_pct', 0)
        sharpe = p.get('sharpe_ratio', 0)
        trades = p.get('total_trades', 0)
        forward = p.get('forward_result', 0)
        back = p.get('back_result', 0)
        params = p.get('input_params', {})

        # Get equity curve from backtest result
        equity_curve = p.get('equity_curve', [])

        passes_data[str(pass_num)] = {
            'success': True,
            'pass': pass_num,
            'parameters': params,
            'opt': {
                'in_profit': back,
                'fwd_profit': forward,
            },
            'bt': {
                'total_trades': trades,
                'net_profit': profit,
                'profit_factor': pf,
                'max_drawdown_pct': dd,
                'sharpe_ratio': sharpe,
                'recovery_factor': p.get('recovery_factor', 0),
                'win_rate': p.get('win_rate', 0),
                'split': {
                    'in_sample': {'net_profit': 0, 'trades': 0},
                    'forward': {'net_profit': 0, 'trades': 0}
                }
            },
            'equity': {
                'in_sample': equity_curve,
                'forward': []
            },
            'monte_carlo': {
                'confidence': 0,
                'ruin_probability': 0,
                'median_profit': 0,
                'worst_5pct': 0,
                'best_95pct': 0,
            }
        }

    # Count consistent passes
    consistent_count = sum(1 for p in sorted_results if p.get('forward_result', 0) > 0 and p.get('back_result', 0) > 0)

    # Claude analysis
    claude_analysis = state.get('claude_analysis', '')

    # Gate results
    gates = state.get('gates', {})

    return {
        'ea_name': ea_name,
        'symbol': symbol,
        'timeframe': timeframe,
        'from_date': from_date,
        'to_date': to_date,
        'forward_date': forward_date,
        'optimization': {
            'total_passes': len(backtest_results),
            'valid_passes': len(backtest_results),
            'consistent_passes': consistent_count,
            'rejected': {},
            'scatter': scatter_data,
            'insights': [f'Showing {len(backtest_results)} backtested passes (full 4-year equity curves)'],
        },
        'pass_list': pass_list,
        'passes': passes_data,
        'selected_pass': pass_list[0] if pass_list else None,
        'claude_analysis': claude_analysis,
        'gates': gates,
        'thresholds': {
            'min_trades': 50,
            'min_profit_factor': 1.5,
            'max_drawdown_pct': 30.0,
            'min_mc_confidence': 70,
            'max_ruin_probability': 5,
        }
    }



# Legacy dashboard functions (_generate_legacy_dashboard, _workflow_to_report,
# _get_optimization_analysis) were REMOVED - SPA-only approach now.


def generate_all_dashboards(
    runs_dir: str = 'runs',
    open_browser: bool = False,
    run_backtests: bool = False,
) -> list[str]:
    """Generate dashboards for all workflow runs."""
    runs_path = Path(runs_dir)
    generated = []

    for state_file in runs_path.glob('workflow_*.json'):
        try:
            path = generate_dashboard_from_workflow(
                str(state_file),
                open_browser=False,
                run_backtests=run_backtests,
            )
            generated.append(path)
            print(f"Generated: {path}")
        except Exception as e:
            print(f"Error generating dashboard for {state_file.name}: {e}")

    if open_browser and generated:
        import webbrowser
        webbrowser.open(f'file://{Path(generated[0]).absolute()}')

    return generated


if __name__ == '__main__':
    if len(sys.argv) > 1:
        workflow_path = sys.argv[1]
        run_bt = '--backtest' in sys.argv or '-b' in sys.argv
        path = generate_dashboard_from_workflow(
            workflow_path,
            open_browser=True,
            run_backtests=run_bt,
        )
        print(f"Generated: {path}")
    else:
        paths = generate_all_dashboards(open_browser=True)
        print(f"Generated {len(paths)} dashboards")
