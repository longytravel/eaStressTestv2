"""
Leaderboard Generator

Aggregates TOP 20 passes from each workflow run into a combined leaderboard.
Each workflow contributes its best 20 optimization passes.
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

# Direct import to avoid circular dependency
from modules.loader import load_module

_pass_analyzer = load_module("pass_analyzer", "modules/pass_analyzer.py")
analyze_passes = _pass_analyzer.analyze_passes

TEMPLATES_DIR = Path(__file__).parent / 'templates'
PASSES_PER_WORKFLOW = 20


def generate_leaderboard(
    runs_dir: str = 'runs',
    output_dir: Optional[str] = None,
    open_browser: bool = False,
    passes_per_workflow: int = PASSES_PER_WORKFLOW,
) -> str:
    """
    Generate leaderboard from top passes across all workflow runs.

    Each workflow contributes its top N passes to the leaderboard.

    Args:
        runs_dir: Directory containing workflow JSON files
        output_dir: Where to save leaderboard (default: runs/leaderboard/)
        open_browser: Open in browser after generation
        passes_per_workflow: Number of top passes to include per workflow

    Returns:
        Path to generated index.html
    """
    runs_path = Path(runs_dir)

    if output_dir is None:
        output_dir = runs_path / 'leaderboard'
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all passes from all workflows
    all_passes = []
    workflows_processed = 0

    for state_file in sorted(runs_path.glob('workflow_*.json')):
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)

            passes = extract_top_passes(state, state_file, top_n=passes_per_workflow)
            if passes:
                all_passes.extend(passes)
                workflows_processed += 1
                print(f"  Added {len(passes)} passes from {state_file.name}")
        except Exception as e:
            print(f"Error reading {state_file}: {e}")
            continue

    # Sort all passes by composite score descending
    all_passes.sort(key=lambda x: x.get('score_num', 0), reverse=True)

    # Add ranks
    for i, p in enumerate(all_passes, 1):
        p['rank'] = i

    # Build data for template
    data = {
        'passes': all_passes,
        'total_passes': len(all_passes),
        'workflows_processed': workflows_processed,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }

    # Use SPA template
    template_path = TEMPLATES_DIR / 'leaderboard_spa.html'
    if template_path.exists():
        template = template_path.read_text(encoding='utf-8')
        json_data = json.dumps(data, indent=2)
        html = template.replace('{{DATA_JSON}}', json_data)
    else:
        html = _generate_fallback_html(all_passes, data)

    # Write output
    output_path = output_dir / 'index.html'
    output_path.write_text(html, encoding='utf-8')

    # Also save raw data
    data_path = output_dir / 'data.json'
    data_path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    if open_browser:
        import webbrowser
        webbrowser.open(f'file://{output_path.absolute()}')

    return str(output_path)


def extract_top_passes(state: dict, state_file: Path, top_n: int = 20) -> list:
    """Extract top N passes from a workflow state.

    Prefers step 9 backtest results (more accurate) when available,
    falls back to step 7 optimization results.
    """
    steps = state.get('steps', {})

    # First, check if we have step 9 backtest results (preferred)
    bt_step = steps.get('9_backtest_robust', {})
    bt_result = bt_step.get('result', {})
    backtest_results = bt_result.get('all_results', [])

    if backtest_results:
        # Use actual backtest results - more accurate
        return _extract_from_backtests(state, state_file, backtest_results, top_n)

    # Fall back to optimization results
    opt_step = steps.get('7_run_optimization', {})
    opt_result = opt_step.get('result', {})
    all_results = opt_result.get('results', [])

    if not all_results:
        return []

    # Analyze passes
    analysis = analyze_passes(all_results)
    filtered = analysis.get('filtered_passes', [])[:top_n]

    if not filtered:
        return []

    # Extract workflow info
    ea_name = state.get('ea_name', 'Unknown')
    symbol = state.get('symbol', '')
    timeframe = state.get('timeframe', '')
    workflow_id = state.get('workflow_id', state_file.stem)
    created_at = state.get('created_at', '')

    # Build pass entries
    passes = []
    for p in filtered:
        params = p.get('params', {})
        pass_num = params.get('Pass', 0)

        # Determine status based on consistency
        is_consistent = p.get('is_consistent', False)
        forward = p.get('forward_result', 0)
        back = p.get('back_result', 0)

        if is_consistent:
            status = 'consistent'
        elif forward > 0 and back < 0:
            status = 'forward_only'
        elif back > 0 and forward < 0:
            status = 'back_only'
        else:
            status = 'mixed'

        status_labels = {
            'consistent': '✓ Consistent',
            'forward_only': '→ Forward Only',
            'back_only': '← Back Only',
            'mixed': '? Mixed',
        }

        # Filter params for display
        skip_params = {'Pass', 'Forward Result', 'Back Result', 'Custom', 'Result'}
        clean_params = {k: v for k, v in params.items() if k not in skip_params}

        passes.append({
            'ea_name': ea_name,
            'symbol': symbol,
            'timeframe': timeframe,
            'pass_num': pass_num,
            'workflow_id': workflow_id,
            'dashboard_link': f"../dashboards/{workflow_id}/index.html",
            'created_at': created_at,

            # Metrics
            'score': f"{p.get('composite_score', 0):.1f}",
            'score_num': p.get('composite_score', 0),
            'profit': f"£{p.get('profit', 0):,.0f}",
            'profit_num': p.get('profit', 0),
            'profit_factor': f"{p.get('profit_factor', 0):.2f}",
            'pf_num': p.get('profit_factor', 0),
            'max_drawdown_pct': f"{p.get('max_drawdown_pct', 0):.1f}%",
            'dd_num': p.get('max_drawdown_pct', 0),
            'sharpe_ratio': f"{p.get('sharpe_ratio', 0):.1f}",
            'sharpe_num': p.get('sharpe_ratio', 0),
            'total_trades': p.get('total_trades', 0),

            # Forward/Back
            'forward_result': f"{forward:+.1f}" if forward != 0 else "0",
            'forward_num': forward,
            'back_result': f"{back:+.1f}" if back != 0 else "0",
            'back_num': back,
            'is_consistent': is_consistent,

            # Status
            'status': status,
            'status_label': status_labels.get(status, status),

            # Parameters (for details view)
            'parameters': clean_params,
        })

    return passes


def _extract_from_backtests(state: dict, state_file: Path, backtest_results: list, top_n: int) -> list:
    """Extract passes from step 9 backtest results (preferred, more accurate)."""

    ea_name = state.get('ea_name', 'Unknown')
    symbol = state.get('symbol', '')
    timeframe = state.get('timeframe', '')
    workflow_id = state.get('workflow_id', state_file.stem)
    created_at = state.get('created_at', '')

    # Sort by profit descending and take top_n
    sorted_results = sorted(backtest_results, key=lambda x: x.get('profit', 0), reverse=True)[:top_n]

    passes = []
    for p in sorted_results:
        pass_num = p.get('pass_num', 0)
        profit = p.get('profit', 0)
        pf = p.get('profit_factor', 0)
        dd = p.get('max_drawdown_pct', 0)
        sharpe = p.get('sharpe_ratio', 0)
        trades = p.get('total_trades', 0)
        forward = p.get('forward_result', 0)
        back = p.get('back_result', 0)

        # Calculate composite score
        score = 0
        if pf >= 1.5: score += 3
        elif pf >= 1.2: score += 2
        elif pf >= 1.0: score += 1
        if sharpe >= 1.0: score += 2
        elif sharpe >= 0.5: score += 1
        if dd <= 20: score += 2
        elif dd <= 30: score += 1
        if trades >= 100: score += 1
        is_consistent = forward > 0 and back > 0
        if is_consistent: score += 2

        # Determine status
        if is_consistent:
            status = 'consistent'
        elif forward > 0 and back < 0:
            status = 'forward_only'
        elif back > 0 and forward < 0:
            status = 'back_only'
        else:
            status = 'mixed'

        status_labels = {
            'consistent': '✓ Consistent',
            'forward_only': '→ Forward Only',
            'back_only': '← Back Only',
            'mixed': '? Mixed',
        }

        # Clean params for display
        input_params = p.get('input_params', {})
        skip_params = {'Pass', 'Forward Result', 'Back Result', 'Custom', 'Result',
                       'Use_Price_Slope_Filter', 'Use_RSI_Slope_Filter'}
        clean_params = {k: v for k, v in input_params.items() if k not in skip_params}

        passes.append({
            'ea_name': ea_name,
            'symbol': symbol,
            'timeframe': timeframe,
            'pass_num': pass_num,
            'workflow_id': workflow_id,
            'dashboard_link': f"../dashboards/{workflow_id}/index.html",
            'created_at': created_at,

            # Metrics from actual backtest (more accurate!)
            'score': f"{score:.1f}",
            'score_num': score,
            'profit': f"£{profit:,.0f}",
            'profit_num': profit,
            'profit_factor': f"{pf:.2f}",
            'pf_num': pf,
            'max_drawdown_pct': f"{dd:.1f}%",
            'dd_num': dd,
            'sharpe_ratio': f"{sharpe:.1f}",
            'sharpe_num': sharpe,
            'total_trades': trades,

            # Forward/Back (from optimization)
            'forward_result': f"{forward:+.1f}" if forward != 0 else "0",
            'forward_num': forward,
            'back_result': f"{back:+.1f}" if back != 0 else "0",
            'back_num': back,
            'is_consistent': is_consistent,

            # Status
            'status': status,
            'status_label': status_labels.get(status, status),

            # Parameters
            'parameters': clean_params,

            # Mark as backtested
            'backtested': True,
        })

    return passes


def _generate_fallback_html(passes: list, data: dict) -> str:
    """Generate minimal HTML fallback."""
    rows = []
    for p in passes[:50]:
        rows.append(f"""
        <tr>
            <td>{p['rank']}</td>
            <td>{p['ea_name']}</td>
            <td>{p['pass_num']}</td>
            <td>{p['total_trades']}</td>
            <td>{p['profit']}</td>
            <td>{p['profit_factor']}</td>
            <td>{p['max_drawdown_pct']}</td>
            <td>{p['forward_result']}</td>
            <td>{p['back_result']}</td>
            <td>{p['status_label']}</td>
        </tr>
        """)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>EA Leaderboard</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background: #f5f5f5; }}
        </style>
    </head>
    <body>
        <h1>EA Stress Test Leaderboard</h1>
        <p>{data['total_passes']} passes from {data['workflows_processed']} workflows</p>
        <p>Updated: {data['updated_at']}</p>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>EA</th>
                    <th>Pass</th>
                    <th>Trades</th>
                    <th>Profit</th>
                    <th>PF</th>
                    <th>DD%</th>
                    <th>FWD</th>
                    <th>Back</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </body>
    </html>
    """


if __name__ == '__main__':
    print("Generating leaderboard...")
    path = generate_leaderboard(open_browser=True)
    print(f"Leaderboard generated: {path}")
