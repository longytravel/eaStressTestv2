"""
Pass Backtest Runner

Re-runs backtests for top optimization passes to get full equity data.
This enables per-trade equity curves and proper forward/back test visualization.
"""
import json
import sys
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

# Direct imports to avoid circular dependency through modules/__init__.py
from modules.loader import load_module, get_modules_dir

_modules_dir = get_modules_dir()
_engine_dir = Path(__file__).parent.parent / "engine"

_backtest = load_module("backtest", _modules_dir / "backtest.py")
run_backtest = _backtest.run_backtest
create_backtest_ini = _backtest.create_backtest_ini

_trade_extractor = load_module("trade_extractor", _modules_dir / "trade_extractor.py")
extract_trades = _trade_extractor.extract_trades
compute_equity_curve = _trade_extractor.compute_equity_curve
split_trades_by_date = _trade_extractor.split_trades_by_date
generate_chart_data = _trade_extractor.generate_chart_data
Trade = _trade_extractor.Trade

_monte_carlo = load_module("monte_carlo", _modules_dir / "monte_carlo.py")
run_monte_carlo = _monte_carlo.run_monte_carlo

_pass_analyzer = load_module("pass_analyzer", _modules_dir / "pass_analyzer.py")
analyze_passes = _pass_analyzer.analyze_passes

_terminals = load_module("terminals", _engine_dir / "terminals.py")
TerminalRegistry = _terminals.TerminalRegistry

import settings


@dataclass
class PassBacktestResult:
    """Result of backtesting a single optimization pass with extended metrics."""
    success: bool
    pass_number: int
    parameters: Dict[str, Any]

    # From optimization
    opt_in_profit: float = 0.0
    opt_fwd_profit: float = 0.0
    opt_in_pf: float = 0.0
    opt_fwd_pf: float = 0.0

    # From backtest re-run - Core metrics
    report_path: Optional[str] = None
    total_trades: int = 0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    recovery_factor: float = 0.0
    win_rate: float = 0.0
    expected_payoff: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    # Extended: Statistical
    z_score: float = 0.0
    z_score_confidence: float = 0.0

    # Extended: Returns
    ahpr: float = 0.0
    ghpr: float = 0.0

    # Extended: Linear Regression
    lr_correlation: float = 0.0
    lr_standard_error: float = 0.0

    # Extended: Drawdown details
    drawdown: Dict[str, float] = None

    # Extended: Streaks
    streaks: Dict[str, Any] = None

    # Extended: Trade sizes/positions
    positions: Dict[str, Any] = None

    # Extended: Holding times
    holding_times: Dict[str, str] = None

    # Extended: Costs
    costs: Dict[str, float] = None

    # Extended: Direction
    direction: Dict[str, Any] = None

    # Split metrics
    in_sample_profit: float = 0.0
    in_sample_trades: int = 0
    forward_profit: float = 0.0
    forward_trades: int = 0

    # Equity curves (trade-by-trade)
    equity_in_sample: List[float] = None
    equity_forward: List[float] = None

    # Chart data
    charts: Dict[str, Any] = None

    # Monte Carlo results
    mc_confidence: float = 0.0
    mc_ruin_probability: float = 0.0
    mc_median_profit: float = 0.0
    mc_worst_5pct: float = 0.0
    mc_best_95pct: float = 0.0

    error: Optional[str] = None

    def __post_init__(self):
        if self.equity_in_sample is None:
            self.equity_in_sample = []
        if self.equity_forward is None:
            self.equity_forward = []
        if self.drawdown is None:
            self.drawdown = {}
        if self.streaks is None:
            self.streaks = {}
        if self.positions is None:
            self.positions = {}
        if self.holding_times is None:
            self.holding_times = {}
        if self.costs is None:
            self.costs = {}
        if self.direction is None:
            self.direction = {}
        if self.charts is None:
            self.charts = {}

    def to_dict(self) -> dict:
        return asdict(self)


def backtest_top_passes(
    workflow_state: dict,
    top_n: int = None,
    timeout_per_pass: int = 300,
    terminal: Optional[dict] = None,
) -> Dict[int, PassBacktestResult]:
    """
    Re-run backtests for top N optimization passes.

    Args:
        workflow_state: Full workflow state dict
        top_n: Number of top passes to backtest
        timeout_per_pass: Max seconds per backtest
        terminal: Terminal config (auto-detected if None)

    Returns:
        Dict mapping pass_number -> PassBacktestResult
    """
    # Use default from settings if not specified
    if top_n is None:
        top_n = settings.TOP_PASSES_BACKTEST

    # Get terminal
    if terminal is None:
        registry = TerminalRegistry()
        terminal = registry.get_terminal()

    # Extract workflow info - use compiled EA path from step 2
    steps = workflow_state.get('steps', {})
    compile_step = steps.get('2_compile', {}).get('result', {})
    ea_path = compile_step.get('exe_path', workflow_state.get('ea_path', ''))
    symbol = workflow_state.get('symbol', 'EURUSD')
    timeframe = workflow_state.get('timeframe', 'H1')

    # Get forward date split
    backtest_dates = workflow_state.get('backtest_dates', {})
    forward_date = backtest_dates.get('split', settings.get_backtest_dates()['split'])

    # Get optimization results (reuse steps from above)
    opt_step = steps.get('7_run_optimization', {})
    opt_result = opt_step.get('result', {})
    all_results = opt_result.get('results', [])

    if not all_results:
        return {}

    # Analyze and filter passes
    analysis = analyze_passes(all_results)
    filtered_passes = analysis.get('filtered_passes', [])[:top_n]

    results: Dict[int, PassBacktestResult] = {}

    for pass_data in filtered_passes:
        params = pass_data.get('params', {})
        pass_number = params.get('Pass', 0)

        # Extract optimization metrics
        opt_in_profit = pass_data.get('back_result', 0)
        opt_fwd_profit = pass_data.get('forward_result', 0)

        # Build parameter dict (filter out metadata)
        skip_params = {'Pass', 'Forward Result', 'Back Result', 'Custom', 'Result'}
        input_params = {k: v for k, v in params.items() if k not in skip_params}

        # Run backtest
        bt_result = run_backtest(
            ea_path=ea_path,
            symbol=symbol,
            timeframe=timeframe,
            params=input_params,
            terminal=terminal,
            timeout=timeout_per_pass,
        )

        if not bt_result.get('success'):
            results[pass_number] = PassBacktestResult(
                success=False,
                pass_number=pass_number,
                parameters=input_params,
                opt_in_profit=opt_in_profit,
                opt_fwd_profit=opt_fwd_profit,
                error='; '.join(bt_result.get('errors', ['Unknown error']))
            )
            continue

        # Extract trades from report
        report_path = bt_result.get('report_path')
        trades_result = extract_trades(report_path) if report_path else None

        if not trades_result or not trades_result.success:
            # Still return backtest metrics even if trade extraction failed
            results[pass_number] = PassBacktestResult(
                success=True,
                pass_number=pass_number,
                parameters=input_params,
                opt_in_profit=opt_in_profit,
                opt_fwd_profit=opt_fwd_profit,
                report_path=report_path,
                total_trades=bt_result.get('total_trades', 0),
                net_profit=bt_result.get('profit', 0),
                profit_factor=bt_result.get('profit_factor', 0),
                max_drawdown_pct=bt_result.get('max_drawdown_pct', 0),
                sharpe_ratio=bt_result.get('sharpe_ratio', 0),
                recovery_factor=bt_result.get('recovery_factor', 0),
                win_rate=bt_result.get('win_rate', 0),
                error='Trade extraction failed - using backtest metrics only'
            )
            continue

        # Split trades by forward date
        trades = trades_result.trades
        in_sample_trades, forward_trades = split_trades_by_date(trades, forward_date)

        # Compute equity curves
        initial_balance = trades_result.initial_balance or settings.DEPOSIT
        equity_in_sample = compute_equity_curve(in_sample_trades, initial_balance)

        # Forward equity starts from where in-sample ended
        forward_start = equity_in_sample[-1] if equity_in_sample else initial_balance
        equity_forward = compute_equity_curve(forward_trades, forward_start)

        # Calculate split metrics
        in_sample_profit = sum(t.net_profit for t in in_sample_trades)
        forward_profit = sum(t.net_profit for t in forward_trades)

        # Run Monte Carlo on all trades
        mc_result = run_monte_carlo(
            trades=[t.net_profit for t in trades],
            initial_balance=initial_balance,
        )

        # Generate chart data for this pass
        chart_data = generate_chart_data(trades)

        results[pass_number] = PassBacktestResult(
            success=True,
            pass_number=pass_number,
            parameters=input_params,
            opt_in_profit=opt_in_profit,
            opt_fwd_profit=opt_fwd_profit,
            report_path=report_path,
            # Core metrics
            total_trades=len(trades),
            net_profit=trades_result.total_net_profit,
            profit_factor=bt_result.get('profit_factor', 0),
            max_drawdown_pct=bt_result.get('max_drawdown_pct', 0),
            sharpe_ratio=bt_result.get('sharpe_ratio', 0),
            recovery_factor=bt_result.get('recovery_factor', 0),
            win_rate=bt_result.get('win_rate', 0),
            expected_payoff=bt_result.get('expected_payoff', 0),
            gross_profit=bt_result.get('gross_profit', 0),
            gross_loss=bt_result.get('gross_loss', 0),
            # Extended: Statistical
            z_score=bt_result.get('z_score', 0),
            z_score_confidence=bt_result.get('z_score_confidence', 0),
            # Extended: Returns
            ahpr=bt_result.get('ahpr', 0),
            ghpr=bt_result.get('ghpr', 0),
            # Extended: Linear Regression
            lr_correlation=bt_result.get('lr_correlation', 0),
            lr_standard_error=bt_result.get('lr_standard_error', 0),
            # Extended: Drawdown details
            drawdown=bt_result.get('drawdown', {}),
            # Extended: Streaks
            streaks=bt_result.get('streaks', {}),
            # Extended: Positions
            positions=bt_result.get('positions', {}),
            # Extended: Holding times
            holding_times=bt_result.get('holding_times', {}),
            # Extended: Costs
            costs=bt_result.get('costs', {}),
            # Extended: Direction
            direction=bt_result.get('direction', {}),
            # Split metrics
            in_sample_profit=in_sample_profit,
            in_sample_trades=len(in_sample_trades),
            forward_profit=forward_profit,
            forward_trades=len(forward_trades),
            # Equity curves
            equity_in_sample=equity_in_sample,
            equity_forward=equity_forward,
            # Chart data
            charts=chart_data,
            # Monte Carlo
            mc_confidence=mc_result.get('confidence', 0),
            mc_ruin_probability=mc_result.get('ruin_probability', 0),
            mc_median_profit=mc_result.get('median_profit', 0),
            mc_worst_5pct=mc_result.get('worst_case', 0),
            mc_best_95pct=mc_result.get('best_case', 0),
        )

        # Small delay between backtests to let terminal settle
        time.sleep(2)

    return results


def prepare_dashboard_data(
    workflow_state: dict,
    pass_results: Dict[int, PassBacktestResult],
) -> dict:
    """
    Prepare all data needed for the interactive dashboard.

    Args:
        workflow_state: Full workflow state
        pass_results: Results from backtest_top_passes()

    Returns:
        Dict ready to be embedded as JSON in the dashboard HTML
    """
    # Basic info
    ea_name = workflow_state.get('ea_name', 'Unknown')
    symbol = workflow_state.get('symbol', 'EURUSD')
    timeframe = workflow_state.get('timeframe', 'H1')

    backtest_dates = workflow_state.get('backtest_dates', {})
    from_date = backtest_dates.get('start', '')
    to_date = backtest_dates.get('end', '')
    forward_date = backtest_dates.get('split', '')

    # Get optimization summary
    steps = workflow_state.get('steps', {})
    opt_step = steps.get('7_run_optimization', {})
    opt_result = opt_step.get('result', {})
    all_results = opt_result.get('results', [])

    analysis = analyze_passes(all_results)

    # Build scatter plot data (in-sample vs forward profit)
    scatter_data = []
    for p in analysis.get('filtered_passes', []):
        scatter_data.append({
            'x': p.get('back_result', 0),
            'y': p.get('forward_result', 0),
        })

    # Build pass list and details - include ALL valid passes from optimization
    passes_data = {}
    pass_list = []

    # First add all valid passes from optimization (basic data)
    skip_params = {'Pass', 'Forward Result', 'Back Result', 'Custom', 'Result'}
    for p in analysis.get('filtered_passes', []):
        params = p.get('params', {})
        pass_num = params.get('Pass', 0)
        pass_list.append(pass_num)

        clean_params = {k: v for k, v in params.items() if k not in skip_params}

        passes_data[str(pass_num)] = {
            'success': True,
            'pass': pass_num,
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
                'win_rate': 0,
                'expected_payoff': 0,
                'gross_profit': 0,
                'gross_loss': 0,
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
            },
            'error': None,
        }

    # Then overlay backtested passes with full details (equity curves, monte carlo, extended metrics)
    for pass_num, result in pass_results.items():
        passes_data[str(pass_num)] = {
            'success': result.success,
            'pass': pass_num,
            'parameters': result.parameters,
            'opt': {
                'in_profit': result.opt_in_profit,
                'fwd_profit': result.opt_fwd_profit,
            },
            'bt': {
                'report_path': result.report_path,
                'total_trades': result.total_trades,
                'net_profit': result.net_profit,
                'profit_factor': result.profit_factor,
                'max_drawdown_pct': result.max_drawdown_pct,
                'sharpe_ratio': result.sharpe_ratio,
                'recovery_factor': result.recovery_factor,
                'win_rate': result.win_rate,
                'expected_payoff': result.expected_payoff,
                'gross_profit': result.gross_profit,
                'gross_loss': result.gross_loss,
                'split': {
                    'in_sample': {
                        'net_profit': result.in_sample_profit,
                        'trades': result.in_sample_trades,
                    },
                    'forward': {
                        'net_profit': result.forward_profit,
                        'trades': result.forward_trades,
                    }
                }
            },
            # Extended: Advanced Statistics
            'advanced': {
                'z_score': result.z_score,
                'z_score_confidence': result.z_score_confidence,
                'ahpr': result.ahpr,
                'ghpr': result.ghpr,
                'lr_correlation': result.lr_correlation,
                'lr_standard_error': result.lr_standard_error,
            },
            # Extended: Drawdown details
            'drawdown': result.drawdown,
            # Extended: Streaks
            'streaks': result.streaks,
            # Extended: Position analysis
            'positions': result.positions,
            # Extended: Holding times
            'holding_times': result.holding_times,
            # Extended: Costs
            'costs': result.costs,
            # Extended: Direction
            'direction': result.direction,
            # Equity curves
            'equity': {
                'in_sample': result.equity_in_sample,
                'forward': result.equity_forward,
            },
            # Chart data for profit histogram, MFE/MAE, holding times
            'charts': result.charts,
            # Monte Carlo
            'monte_carlo': {
                'confidence': result.mc_confidence,
                'ruin_probability': result.mc_ruin_probability,
                'median_profit': result.mc_median_profit,
                'worst_5pct': result.mc_worst_5pct,
                'best_95pct': result.mc_best_95pct,
            },
            'error': result.error,
        }

    # Claude analysis (if available)
    claude_analysis = workflow_state.get('claude_analysis', {})

    # Gate results
    gates = workflow_state.get('gates', {})

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
            'min_trades': settings.MIN_TRADES,
            'min_profit_factor': settings.MIN_PROFIT_FACTOR,
            'max_drawdown_pct': settings.MAX_DRAWDOWN_PCT,
            'min_mc_confidence': 70,
            'max_ruin_probability': 5,
        }
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python pass_backtest.py <workflow_json> [top_n]")
        print("\nRe-runs backtests for top optimization passes.")
        sys.exit(1)

    workflow_path = sys.argv[1]
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    with open(workflow_path, 'r') as f:
        state = json.load(f)

    print(f"Running backtests for top {top_n} passes...")
    results = backtest_top_passes(state, top_n=top_n)

    print(f"\nCompleted {len(results)} backtests:")
    for pass_num, result in results.items():
        status = "OK" if result.success else "FAIL"
        print(f"  Pass {pass_num}: {status} - {len(result.equity_in_sample)} IS trades, {len(result.equity_forward)} FWD trades")

    # Prepare dashboard data
    data = prepare_dashboard_data(state, results)

    # Save to JSON file
    output_path = Path(workflow_path).parent / f"dashboard_data_{Path(workflow_path).stem}.json"
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nDashboard data saved to: {output_path}")
