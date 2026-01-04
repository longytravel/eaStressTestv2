"""
Stats Analyzer Module

Prepares optimization data for Claude analysis and saves results.
Claude analyzes the data during conversation, not via code heuristics.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import settings


def prepare_analysis_data(workflow_path: str) -> dict:
    """
    Extract and format key data from workflow for Claude to analyze.

    Returns structured data that Claude can read and analyze.
    Includes extended metrics from backtest results.
    """
    with open(workflow_path, 'r') as f:
        state = json.load(f)

    # Basic info
    data = {
        'ea_name': state.get('ea_name', 'Unknown'),
        'symbol': state.get('symbol', ''),
        'timeframe': state.get('timeframe', ''),
        'status': state.get('status', 'unknown'),
        'dates': state.get('backtest_dates', {}),
    }

    # Final metrics
    data['metrics'] = state.get('metrics', {})

    # Gates
    gates = state.get('gates', {})
    data['gates'] = {
        name: {
            'passed': g.get('passed'),
            'value': g.get('value'),
            'threshold': g.get('threshold'),
        }
        for name, g in gates.items()
    }

    # Optimization results
    steps = state.get('steps', {})
    opt_step = steps.get('7_run_optimization', {})
    opt_result = opt_step.get('result', {})
    all_results = opt_result.get('results', [])

    # Analyze passes
    if all_results:
        # Count by trade threshold
        low_trades = sum(1 for r in all_results if r.get('total_trades', 0) < settings.MIN_TRADES)
        valid = [r for r in all_results if r.get('total_trades', 0) >= settings.MIN_TRADES and r.get('profit_factor', 0) >= 1.0]

        # Find consistent passes (both forward and back positive)
        consistent = []
        for r in valid:
            params = r.get('params', {})
            fwd = params.get('Forward Result', 0)
            back = params.get('Back Result', 0)
            if fwd > 0 and back > 0:
                consistent.append({
                    'trades': r.get('total_trades'),
                    'profit': r.get('profit'),
                    'pf': r.get('profit_factor'),
                    'sharpe': r.get('sharpe_ratio'),
                    'dd_pct': r.get('max_drawdown_pct'),
                    'forward': fwd,
                    'back': back,
                    'params': {k: v for k, v in params.items()
                              if k not in {'Pass', 'Forward Result', 'Back Result', 'Custom'}},
                })

        # Top 10 by various criteria
        valid_sorted = sorted(valid, key=lambda x: x.get('profit', 0), reverse=True)[:10]

        data['optimization'] = {
            'total_passes': len(all_results),
            'rejected_low_trades': low_trades,
            'valid_passes': len(valid),
            'consistent_passes': len(consistent),
            'consistent_details': consistent[:5],  # Top 5 consistent
            'top_by_profit': [
                {
                    'trades': r.get('total_trades'),
                    'profit': r.get('profit'),
                    'pf': r.get('profit_factor'),
                    'dd': r.get('max_drawdown_pct'),
                    'fwd': r.get('params', {}).get('Forward Result'),
                    'back': r.get('params', {}).get('Back Result'),
                }
                for r in valid_sorted
            ],
        }

    # Extended metrics from backtested passes (step 9)
    bt_step = steps.get('9_backtest_robust', {})
    bt_result = bt_step.get('result', {})
    backtest_results = bt_result.get('all_results', [])

    if backtest_results:
        # Extract extended metrics from top backtested passes
        extended = []
        for p in backtest_results[:10]:  # Top 10 backtested
            extended.append({
                'pass': p.get('pass_num', 0),
                'profit': p.get('profit', 0),
                'pf': p.get('profit_factor', 0),
                'dd': p.get('max_drawdown_pct', 0),
                'sharpe': p.get('sharpe_ratio', 0),
                'recovery': p.get('recovery_factor', 0),
                'win_rate': p.get('win_rate', 0),
                # Extended: Statistical
                'z_score': p.get('z_score', 0),
                'ahpr': p.get('ahpr', 0),
                'ghpr': p.get('ghpr', 0),
                'lr_correlation': p.get('lr_correlation', 0),
                # Extended: Streaks
                'max_win_streak': p.get('streaks', {}).get('max_consecutive_wins', 0),
                'max_loss_streak': p.get('streaks', {}).get('max_consecutive_losses', 0),
                # Extended: Costs
                'total_costs': (p.get('costs', {}).get('total_commission', 0) +
                               p.get('costs', {}).get('total_swap', 0)),
                # Monte Carlo
                'mc_confidence': p.get('mc_confidence', 0),
                'mc_ruin': p.get('mc_ruin_probability', 0),
            })

        data['backtested'] = {
            'count': len(backtest_results),
            'passes': extended,
        }

    return data


def format_for_claude(data: dict) -> str:
    """Format the data as a readable report for Claude to analyze.

    Includes extended metrics from backtested passes for deeper analysis.
    """
    lines = []

    lines.append(f"# EA Analysis Request: {data['ea_name']}")
    lines.append(f"Symbol: {data['symbol']} | Timeframe: {data['timeframe']}")
    lines.append(f"Period: {data['dates'].get('start')} to {data['dates'].get('end')}")
    lines.append(f"Forward test from: {data['dates'].get('split')}")
    lines.append("")

    lines.append("## Final Backtest Results")
    m = data.get('metrics', {})
    lines.append(f"- Profit Factor: {m.get('profit_factor', 0):.2f}")
    lines.append(f"- Max Drawdown: {m.get('max_drawdown_pct', 0):.1f}%")
    lines.append(f"- Total Trades: {m.get('total_trades', 0)}")
    lines.append(f"- Sharpe Ratio: {m.get('sharpe_ratio', 0):.2f}")
    lines.append(f"- Net Profit: £{m.get('profit', 0):,.0f}")
    lines.append("")

    lines.append("## Gate Results")
    for name, g in data.get('gates', {}).items():
        status = "PASS" if g['passed'] else "FAIL"
        lines.append(f"- {name}: {status} ({g['value']} vs threshold {g['threshold']})")
    lines.append("")

    opt = data.get('optimization', {})
    if opt:
        lines.append("## Optimization Summary")
        lines.append(f"- Total passes: {opt['total_passes']:,}")
        lines.append(f"- Rejected (< {settings.MIN_TRADES} trades): {opt['rejected_low_trades']:,}")
        lines.append(f"- Valid passes: {opt['valid_passes']}")
        lines.append(f"- Consistent (both forward+back positive): {opt['consistent_passes']}")
        lines.append("")

        if opt.get('consistent_details'):
            lines.append("## Consistent Passes (Forward AND Back positive)")
            for i, p in enumerate(opt['consistent_details'], 1):
                lines.append(f"\n### Pass {i}")
                lines.append(f"Trades: {p['trades']} | Profit: £{p['profit']:.0f} | PF: {p['pf']:.2f}")
                lines.append(f"Forward: +{p['forward']:.1f} | Back: +{p['back']:.1f}")
                lines.append(f"Drawdown: {p['dd_pct']:.1f}% | Sharpe: {p['sharpe']:.1f}")
                lines.append("Parameters:")
                for k, v in p['params'].items():
                    lines.append(f"  {k}: {v}")
        else:
            lines.append("## WARNING: No consistent passes found!")
            lines.append("No parameter set was profitable in BOTH back and forward tests.")

        if opt.get('top_by_profit'):
            lines.append("\n## Top 10 Valid Passes by Profit")
            lines.append("Trades | Profit | PF | DD% | Forward | Back")
            lines.append("-" * 50)
            for p in opt['top_by_profit']:
                fwd = f"+{p['fwd']:.1f}" if p['fwd'] and p['fwd'] > 0 else f"{p['fwd']:.1f}" if p['fwd'] else "?"
                back = f"+{p['back']:.1f}" if p['back'] and p['back'] > 0 else f"{p['back']:.1f}" if p['back'] else "?"
                lines.append(f"{p['trades']:>6} | £{p['profit']:>6.0f} | {p['pf']:.2f} | {p['dd']:.1f}% | {fwd:>7} | {back:>7}")

    # Extended metrics from backtested passes
    bt = data.get('backtested', {})
    if bt.get('passes'):
        lines.append("\n## Extended Analysis (Top Backtested Passes)")
        lines.append(f"Re-backtested {bt['count']} passes with full metrics")
        lines.append("")
        lines.append("### Advanced Statistics Summary")
        lines.append("Pass | Profit | Z-Score | AHPR | LR Corr | MC Conf | MC Ruin")
        lines.append("-" * 70)
        for p in bt['passes'][:5]:
            lines.append(
                f"{p['pass']:>4} | £{p['profit']:>6.0f} | "
                f"{p['z_score']:>6.2f} | {p['ahpr']:.4f} | "
                f"{p['lr_correlation']:.3f} | {p['mc_confidence']:>5.1f}% | {p['mc_ruin']:>5.1f}%"
            )

        lines.append("\n### Streak & Cost Analysis")
        lines.append("Pass | Win Streak | Loss Streak | Total Costs")
        lines.append("-" * 50)
        for p in bt['passes'][:5]:
            lines.append(
                f"{p['pass']:>4} | "
                f"{p['max_win_streak']:>10} | {p['max_loss_streak']:>11} | £{p['total_costs']:>8.0f}"
            )

    lines.append("\n---")
    lines.append("Please analyze this EA's optimization results and provide:")
    lines.append("1. GO/NO-GO decision for live trading")
    lines.append("2. Key concerns or red flags (especially from Z-Score, LR Correlation, Monte Carlo)")
    lines.append("3. If viable, which parameter set to use and why")
    lines.append("4. Assessment of robustness based on extended metrics")
    lines.append("5. Specific improvements to investigate")

    return '\n'.join(lines)


def save_claude_analysis(workflow_path: str, analysis_text: str) -> str:
    """Save Claude's analysis to the workflow state and regenerate dashboard."""
    with open(workflow_path, 'r') as f:
        state = json.load(f)

    state['claude_analysis'] = analysis_text
    state['claude_analysis_at'] = datetime.now().isoformat()

    with open(workflow_path, 'w') as f:
        json.dump(state, f, indent=2)

    return workflow_path


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python stats_analyzer.py <workflow_json>")
        sys.exit(1)

    data = prepare_analysis_data(sys.argv[1])
    report = format_for_claude(data)
    print(report)
