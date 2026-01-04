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
import settings

# Direct import to avoid circular dependency through modules/__init__.py
from modules.loader import load_module

_pass_analyzer = load_module("pass_analyzer", "modules/pass_analyzer.py")
analyze_passes = _pass_analyzer.analyze_passes

_gates = load_module("gates", "engine/gates.py")
calculate_composite_score = _gates.calculate_composite_score


def _load_results_file(results_file: str, state_file: Path = None) -> list:
    """Load results from a separate JSON file.

    Results may be stored relative to runs dir or as absolute path.
    """
    if not results_file:
        return []

    results_path = Path(results_file)

    # Try as-is first
    if results_path.exists():
        with open(results_path, 'r') as f:
            data = json.load(f)
        # Handle both direct list and dict with 'all_results' or 'results' key
        if isinstance(data, list):
            return data
        return data.get('all_results', data.get('results', []))

    # Try relative to state file's parent if provided
    if state_file:
        relative_path = state_file.parent / results_file
        if relative_path.exists():
            with open(relative_path, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return data.get('all_results', data.get('results', []))

    return []


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
    state_file = Path(workflow_path)
    with open(state_file, 'r') as f:
        state = json.load(f)

    # Determine workflow ID
    workflow_id = state.get('workflow_id', '')
    if not workflow_id:
        workflow_id = state_file.stem

    # Prepare dashboard data
    if run_backtests:
        # Run backtests for top passes to get equity curves
        from reports.pass_backtest import backtest_top_passes, prepare_dashboard_data
        pass_results = backtest_top_passes(state, top_n=top_n)
        data = prepare_dashboard_data(state, pass_results)
    else:
        # Use optimization data only (fast but no per-trade equity)
        data = prepare_data_from_optimization(state, state_file)

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


def prepare_data_from_optimization(state: dict, state_file: Path = None) -> dict:
    """
    Prepare dashboard data from workflow state.

    Prefers step 9 backtest results when available (more accurate),
    falls back to step 7 optimization results.

    Results may be inline or stored in separate files (results_file).
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

    # Load from file if not inline
    if not backtest_results and bt_result.get('results_file'):
        backtest_results = _load_results_file(bt_result['results_file'], state_file)

    if backtest_results:
        # Use actual backtest results
        return _prepare_data_from_backtests(state, backtest_results)

    # Fall back to optimization results
    opt_step = steps.get('7_run_optimization', {})
    opt_result = opt_step.get('result', {})
    all_results = opt_result.get('results', [])

    # Load from file if not inline
    if not all_results and opt_result.get('results_file'):
        all_results = _load_results_file(opt_result['results_file'], state_file)

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

    # Sort optimization-only view by the leaderboard composite score (not the deprecated pass_analyzer score)
    filtered_passes = list(analysis.get('filtered_passes', []) or [])
    if filtered_passes:
        for p in filtered_passes:
            score_metrics = {
                'profit_factor': p.get('profit_factor', 0),
                'max_drawdown': p.get('max_drawdown_pct', 0),
                'sharpe_ratio': p.get('sharpe_ratio', 0),
                'sortino_ratio': p.get('sortino_ratio', 0),
                'calmar_ratio': p.get('calmar_ratio', 0),
                'recovery_factor': p.get('recovery_factor', 0),
                'expected_payoff': p.get('expected_payoff', 0),
                'win_rate': p.get('win_rate', 0),
                'param_stability': 0.5,
            }
            score = calculate_composite_score(score_metrics)
            if p.get('is_consistent'):
                score = min(10, score + 0.5)
            p['leaderboard_score'] = score

        filtered_passes.sort(key=lambda x: (x.get('leaderboard_score', 0), x.get('profit', 0)), reverse=True)

    # Build scatter data
    scatter_data = []
    for p in filtered_passes:
        scatter_data.append({
            # Profit split: in-sample (main OPT report) vs forward (forward OPT report)
            'x': p.get('profit', 0),
            'y': p.get('forward_profit', 0),
        })

    # Build pass data from optimization (simplified - no equity curves)
    pass_list = []
    passes_data = {}

    for p in filtered_passes[:50]:  # Top 50
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
                'in_profit': p.get('profit', 0),
                'fwd_profit': p.get('forward_profit', 0),
            },
            'bt': {
                'total_trades': p.get('total_trades', 0),
                'net_profit': p.get('profit', 0),
                'profit_factor': p.get('profit_factor', 0),
                'max_drawdown_pct': p.get('max_drawdown_pct', 0),
                'sharpe_ratio': p.get('sharpe_ratio', 0),
                'recovery_factor': p.get('recovery_factor', 0),
                'win_rate': 0,
                'expected_payoff': 0,
                'gross_profit': 0,
                'gross_loss': 0,
                'data_quality': {},
                'split': {
                    'in_sample': {'net_profit': 0, 'trades': 0},
                    'forward': {'net_profit': 0, 'trades': 0}
                }
            },
            # Extended: Advanced Statistics (empty for non-backtested)
            'advanced': {
                'z_score': 0,
                'z_score_confidence': 0,
                'ahpr': 0,
                'ghpr': 0,
                'lr_correlation': 0,
                'lr_standard_error': 0,
            },
            # Extended metrics (empty for non-backtested)
            'drawdown': {},
            'streaks': {},
            'positions': {},
            'holding_times': {},
            'costs': {},
            'direction': {},
            # Equity curves
            'equity': {
                'in_sample': [],
                'forward': []
            },
            # Chart data (empty for non-backtested)
            'charts': {},
            # Monte Carlo
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

    step3 = (state.get('steps', {}) or {}).get('3_extract_params', {}) if isinstance(state.get('steps', {}), dict) else {}
    step3_result = step3.get('result', {}) if isinstance(step3.get('result', {}), dict) else {}
    ea_inputs = step3_result.get('params', []) if isinstance(step3_result.get('params', []), list) else []

    return {
        'ea_name': ea_name,
        'symbol': symbol,
        'timeframe': timeframe,
        'from_date': from_date,
        'to_date': to_date,
        'forward_date': forward_date,
        'stress_scenarios': state.get('stress_scenarios', {}),
        'ea_inputs': ea_inputs,
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
        'safety': {
            'max_spread_pips': getattr(settings, 'SAFETY_DEFAULT_MAX_SPREAD_PIPS', 3.0),
            'max_slippage_pips': getattr(settings, 'SAFETY_DEFAULT_MAX_SLIPPAGE_PIPS', 3.0),
        },
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

    steps = state.get('steps', {}) or {}

    # Load optimization results so we can show in-sample vs forward PROFIT (not score)
    opt_step = steps.get('7_run_optimization', {}) if isinstance(steps, dict) else {}
    opt_result = opt_step.get('result', {}) if isinstance(opt_step, dict) else {}
    opt_results = []
    if isinstance(opt_result, dict):
        opt_results = opt_result.get('results', []) or []
        if not opt_results and opt_result.get('results_file'):
            opt_results = _load_results_file(opt_result['results_file'], None) or []

    opt_by_pass = {}
    for r in opt_results:
        params = r.get('params', {}) if isinstance(r, dict) else {}
        pass_num = params.get('Pass')
        if isinstance(pass_num, int):
            opt_by_pass[pass_num] = r

    def _score_for_backtest(p: dict) -> float:
        if not isinstance(p, dict):
            return 0.0
        score = p.get('composite_score')
        if isinstance(score, (int, float)):
            return float(score)

        score_metrics = {
            'profit_factor': p.get('profit_factor', 0),
            'max_drawdown': p.get('max_drawdown_pct', 0),
            'sharpe_ratio': p.get('sharpe_ratio', 0),
            'sortino_ratio': p.get('sortino_ratio', 0),
            'calmar_ratio': p.get('calmar_ratio', 0),
            'recovery_factor': p.get('recovery_factor', 0),
            'expected_payoff': p.get('expected_payoff', 0),
            'win_rate': p.get('win_rate', 0),
            'param_stability': 0.5,
        }
        score = calculate_composite_score(score_metrics)

        # Bonus for positive forward/back optimization results
        forward = p.get('forward_result', 0) or 0
        back = p.get('back_result', 0) or 0
        if forward > 0 and back > 0:
            score = min(10, score + 0.5)

        return float(score)

    selection_metric = getattr(settings, 'BEST_PASS_SELECTION', 'score')
    selection_metric = (selection_metric or 'score').strip().lower()

    # Sort by selection metric (default: leaderboard score)
    if selection_metric == 'profit':
        sorted_results = sorted(
            backtest_results,
            key=lambda x: (float((x or {}).get('profit', 0) or 0), _score_for_backtest(x or {})),
            reverse=True,
        )
    else:
        sorted_results = sorted(
            backtest_results,
            key=lambda x: (_score_for_backtest(x or {}), float((x or {}).get('profit', 0) or 0)),
            reverse=True,
        )

    # Monte Carlo results (workflow-level, computed for the best pass)
    mc_result = (
        (state.get('steps', {}) or {}).get('10_monte_carlo', {}).get('result', {})
        if isinstance(state.get('steps', {}), dict)
        else {}
    )
    # Monte Carlo results are workflow-level; attach them to the pass they were run for.
    best_pass_num = None
    if isinstance(mc_result, dict):
        best_pass_num = mc_result.get('pass_num')
    if best_pass_num is None:
        best_pass_num = sorted_results[0].get('pass_num') if sorted_results else None
    best_monte_carlo = {
        'confidence': 0,
        'ruin_probability': 0,
        'median_profit': 0,
        'worst_5pct': 0,
        'best_95pct': 0,
    }
    if isinstance(mc_result, dict) and mc_result.get('success'):
        best_monte_carlo = {
            'confidence': mc_result.get('confidence', 0),
            'ruin_probability': mc_result.get('ruin_probability', 0),
            'median_profit': mc_result.get('median_profit', 0),
            'worst_5pct': mc_result.get('worst_case', 0),
            'best_95pct': mc_result.get('best_case', 0),
        }

    # Build scatter data
    scatter_data = []
    for p in sorted_results:
        pass_num = p.get('pass_num')
        opt = opt_by_pass.get(pass_num, {}) if isinstance(pass_num, int) else {}
        in_profit = opt.get('profit', 0) if isinstance(opt, dict) else 0
        fwd_profit = opt.get('forward_profit', 0) if isinstance(opt, dict) else 0
        scatter_data.append({
            'x': in_profit,
            'y': fwd_profit,
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
        report_path = p.get('report_path')

        charts = p.get('charts')
        costs = p.get('costs')
        equity_curve = p.get('equity_curve', [])

        needs_charts = not isinstance(charts, dict) or not charts
        needs_costs = not isinstance(costs, dict) or (
            'total_commission' not in costs and 'total_swap' not in costs
        )
        needs_equity = not isinstance(equity_curve, list) or len(equity_curve) < 2

        if report_path and (needs_charts or needs_costs or needs_equity):
            try:
                from modules.trade_extractor import extract_trades, compute_equity_curve, generate_chart_data

                trades_result = extract_trades(str(report_path))
                if trades_result.success and trades_result.trades:
                    if needs_equity:
                        equity_curve = compute_equity_curve(trades_result.trades, trades_result.initial_balance)

                    if needs_charts:
                        charts = generate_chart_data(trades_result.trades)

                    if needs_costs:
                        costs = {
                            'total_commission': trades_result.total_commission,
                            'total_swap': trades_result.total_swap,
                        }
            except Exception:
                # Best-effort backfill for legacy runs; keep existing values on failure.
                pass

        # Get equity curve from backtest result
        in_sample_equity = p.get('equity_curve_in_sample') or equity_curve
        forward_equity = p.get('equity_curve_forward') or []

        opt = opt_by_pass.get(pass_num, {})
        in_profit = opt.get('profit', 0) if isinstance(opt, dict) else 0
        fwd_profit = opt.get('forward_profit', 0) if isinstance(opt, dict) else 0
        if isinstance(opt, dict):
            fwd_trades = opt.get('forward_total_trades', 0) or 0
            total_trades_opt = opt.get('total_trades', 0) or 0
            # Optimizer merges segments by setting total_trades = back + forward
            in_trades = max(0, total_trades_opt - fwd_trades)
        else:
            in_trades = 0
            fwd_trades = 0

        passes_data[str(pass_num)] = {
            'success': True,
            'pass': pass_num,
            'parameters': params,
            'opt': {
                'in_profit': in_profit,
                'fwd_profit': fwd_profit,
            },
            'bt': {
                'total_trades': trades,
                'net_profit': profit,
                'profit_factor': pf,
                'max_drawdown_pct': dd,
                'sharpe_ratio': sharpe,
                'recovery_factor': p.get('recovery_factor', 0),
                'win_rate': p.get('win_rate', 0),
                'expected_payoff': p.get('expected_payoff', 0),
                'gross_profit': p.get('gross_profit', 0),
                'gross_loss': p.get('gross_loss', 0),
                'data_quality': {
                    'history_quality_pct': p.get('history_quality_pct', 0),
                    'bars': p.get('bars', 0),
                    'ticks': p.get('ticks', 0),
                    'symbols': p.get('symbols', 0),
                },
                'split': {
                    'in_sample': {'net_profit': in_profit, 'trades': in_trades},
                    'forward': {'net_profit': fwd_profit, 'trades': fwd_trades},
                }
            },
            # Advanced stats
            'advanced': {
                'z_score': p.get('z_score', 0),
                'z_score_confidence': p.get('z_score_confidence', 0),
                'ahpr': p.get('ahpr', 0),
                'ghpr': p.get('ghpr', 0),
                'lr_correlation': p.get('lr_correlation', 0),
                'lr_standard_error': p.get('lr_standard_error', 0),
            },
            'drawdown': p.get('drawdown', {}),
            'streaks': p.get('streaks', {}),
            'positions': p.get('positions', {}),
            'holding_times': p.get('holding_times', {}),
            'costs': costs if isinstance(costs, dict) else {},
            'direction': p.get('direction', {}),
            'charts': charts if isinstance(charts, dict) else {},
            'equity': {
                'in_sample': in_sample_equity,
                'forward': forward_equity,
            },
            'monte_carlo': {
                **(best_monte_carlo if pass_num == best_pass_num else {}),
            }
        }

            # Count consistent passes
    consistent_count = sum(
        1
        for p in sorted_results
        if (
            isinstance(p.get('pass_num'), int)
            and (opt_by_pass.get(p.get('pass_num'), {}) or {}).get('profit', 0) > 0
            and (opt_by_pass.get(p.get('pass_num'), {}) or {}).get('forward_profit', 0) > 0
        )
    )

    # Claude analysis
    claude_analysis = state.get('claude_analysis', '')

    # Gate results
    gates = state.get('gates', {})

    step3 = (state.get('steps', {}) or {}).get('3_extract_params', {}) if isinstance(state.get('steps', {}), dict) else {}
    step3_result = step3.get('result', {}) if isinstance(step3.get('result', {}), dict) else {}
    ea_inputs = step3_result.get('params', []) if isinstance(step3_result.get('params', []), list) else []

    return {
        'ea_name': ea_name,
        'symbol': symbol,
        'timeframe': timeframe,
        'from_date': from_date,
        'to_date': to_date,
        'forward_date': forward_date,
        'stress_scenarios': state.get('stress_scenarios', {}),
        'forward_windows': state.get('forward_windows', {}),
        'multi_pair_runs': state.get('multi_pair_runs', {}),
        'ea_inputs': ea_inputs,
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
        'safety': {
            'max_spread_pips': getattr(settings, 'SAFETY_DEFAULT_MAX_SPREAD_PIPS', 3.0),
            'max_slippage_pips': getattr(settings, 'SAFETY_DEFAULT_MAX_SLIPPAGE_PIPS', 3.0),
        },
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
