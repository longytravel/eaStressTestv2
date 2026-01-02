"""
Optimization Pass Analyzer

Analyzes all optimization passes with proper filtering and forward/back breakdown.
"""
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
import settings


def analyze_passes(
    results: list[dict],
    min_trades: int = None,
    min_profit_factor: float = None,
    max_drawdown_pct: float = None,
) -> dict:
    """
    Analyze optimization passes with proper filtering.

    Args:
        results: List of pass dicts from optimization
        min_trades: Minimum trades required (default from settings)
        min_profit_factor: Minimum PF (default from settings)
        max_drawdown_pct: Maximum DD% (default from settings)

    Returns:
        dict with:
            - total_passes: int
            - filtered_passes: list (passes meeting criteria)
            - rejected_passes: dict (reason -> count)
            - best_overall: dict (best by composite score)
            - best_forward: dict (best forward test result)
            - best_back: dict (best back test result)
            - best_consistent: dict (best with both forward+back positive)
            - insights: list of strings
    """
    if min_trades is None:
        min_trades = settings.MIN_TRADES
    if min_profit_factor is None:
        min_profit_factor = settings.MIN_PROFIT_FACTOR
    if max_drawdown_pct is None:
        max_drawdown_pct = settings.MAX_DRAWDOWN_PCT

    filtered = []
    rejected = {
        'low_trades': 0,
        'low_pf': 0,
        'high_dd': 0,
        'negative_profit': 0,
    }

    for p in results:
        trades = p.get('total_trades', 0)
        pf = p.get('profit_factor', 0)
        dd = p.get('max_drawdown_pct', 100)
        profit = p.get('profit', 0)

        # Check gates
        if trades < min_trades:
            rejected['low_trades'] += 1
            continue
        if pf < 1.0:
            rejected['low_pf'] += 1
            continue
        if dd > max_drawdown_pct:
            rejected['high_dd'] += 1
            continue
        if profit <= 0:
            rejected['negative_profit'] += 1
            continue

        # Passed all basic filters
        # Extract forward/back results
        params = p.get('params', {})
        p['forward_result'] = params.get('Forward Result', 0)
        p['back_result'] = params.get('Back Result', 0)
        p['is_consistent'] = p['forward_result'] > 0 and p['back_result'] > 0

        # Calculate composite score
        p['composite_score'] = calculate_composite_score(p)

        filtered.append(p)

    # Sort by composite score
    filtered.sort(key=lambda x: x['composite_score'], reverse=True)

    # Find best in each category
    best_overall = filtered[0] if filtered else None

    # Best forward result (among filtered)
    forward_sorted = sorted(filtered, key=lambda x: x['forward_result'], reverse=True)
    best_forward = forward_sorted[0] if forward_sorted else None

    # Best back result
    back_sorted = sorted(filtered, key=lambda x: x['back_result'], reverse=True)
    best_back = back_sorted[0] if back_sorted else None

    # Best consistent (both positive)
    consistent = [p for p in filtered if p['is_consistent']]
    consistent.sort(key=lambda x: min(x['forward_result'], x['back_result']), reverse=True)
    best_consistent = consistent[0] if consistent else None

    # Generate insights
    insights = generate_insights(
        total=len(results),
        filtered=filtered,
        rejected=rejected,
        best_overall=best_overall,
        best_consistent=best_consistent,
    )

    return {
        'total_passes': len(results),
        'filtered_passes': filtered,
        'rejected_passes': rejected,
        'valid_count': len(filtered),
        'consistent_count': len(consistent),
        'best_overall': best_overall,
        'best_forward': best_forward,
        'best_back': best_back,
        'best_consistent': best_consistent,
        'insights': insights,
    }


def calculate_composite_score(p: dict) -> float:
    """
    DEPRECATED: Calculate composite score for a pass.

    NOTE: This function is deprecated. Claude's /stats-analyzer skill now
    provides intelligent pass selection based on EA context, parameter
    relationships, and forward/back test analysis. This function remains
    for backwards compatibility and basic insights generation only.

    Claude should be used for final pass selection, not this Python scoring.
    """
    import warnings
    warnings.warn(
        "calculate_composite_score() is deprecated. "
        "Use Claude /stats-analyzer for intelligent pass selection.",
        DeprecationWarning,
        stacklevel=2
    )
    score = 0

    # Profit factor contribution (0-3 points)
    pf = p.get('profit_factor', 0)
    if pf >= 2.5:
        score += 3
    elif pf >= 2.0:
        score += 2.5
    elif pf >= 1.5:
        score += 2
    elif pf >= 1.2:
        score += 1

    # Sharpe ratio contribution (0-2 points)
    sharpe = p.get('sharpe_ratio', 0)
    if sharpe >= 15:
        score += 2
    elif sharpe >= 10:
        score += 1.5
    elif sharpe >= 5:
        score += 1
    elif sharpe >= 1:
        score += 0.5

    # Drawdown contribution (0-2 points, lower is better)
    dd = p.get('max_drawdown_pct', 100)
    if dd <= 5:
        score += 2
    elif dd <= 10:
        score += 1.5
    elif dd <= 20:
        score += 1
    elif dd <= 30:
        score += 0.5

    # Trade count contribution (0-1 point)
    trades = p.get('total_trades', 0)
    if trades >= 200:
        score += 1
    elif trades >= 100:
        score += 0.7
    elif trades >= 50:
        score += 0.4

    # Consistency bonus (0-2 points)
    forward = p.get('forward_result', 0)
    back = p.get('back_result', 0)
    if forward > 0 and back > 0:
        score += 2
    elif forward > 0 or back > 0:
        score += 0.5

    return round(score, 2)


def generate_insights(
    total: int,
    filtered: list,
    rejected: dict,
    best_overall: Optional[dict],
    best_consistent: Optional[dict],
) -> list[str]:
    """Generate human-readable insights about the optimization results."""
    insights = []

    # Summary
    valid_pct = (len(filtered) / total * 100) if total > 0 else 0
    insights.append(
        f"Of {total:,} optimization passes, only {len(filtered)} ({valid_pct:.1f}%) "
        f"meet minimum requirements."
    )

    # Rejection reasons
    if rejected['low_trades'] > 0:
        pct = rejected['low_trades'] / total * 100
        insights.append(
            f"{rejected['low_trades']:,} passes ({pct:.0f}%) rejected for insufficient trades "
            f"(< {settings.MIN_TRADES})."
        )

    if rejected['low_pf'] > 0:
        insights.append(
            f"{rejected['low_pf']:,} passes rejected for profit factor < 1.0 (losing money)."
        )

    # Best overall
    if best_overall:
        insights.append(
            f"Best overall: {best_overall['total_trades']} trades, "
            f"PF {best_overall['profit_factor']:.2f}, "
            f"£{best_overall['profit']:.0f} profit, "
            f"Sharpe {best_overall['sharpe_ratio']:.1f}."
        )

    # Consistency check
    if best_consistent:
        insights.append(
            f"Best consistent pass (positive in BOTH back+forward): "
            f"Forward={best_consistent['forward_result']:.1f}, "
            f"Back={best_consistent['back_result']:.1f}."
        )
    elif filtered:
        # Check if there are ANY consistent passes
        consistent = [p for p in filtered if p.get('is_consistent', False)]
        if not consistent:
            insights.append(
                "⚠️ WARNING: No passes are profitable in BOTH back AND forward tests! "
                "This suggests overfitting or unstable strategy."
            )

    # Forward vs Back analysis
    if filtered:
        forward_positive = sum(1 for p in filtered if p.get('forward_result', 0) > 0)
        back_positive = sum(1 for p in filtered if p.get('back_result', 0) > 0)

        if forward_positive > back_positive * 2:
            insights.append(
                f"Forward test results much better than back test "
                f"({forward_positive} vs {back_positive} positive). "
                f"May indicate curve-fitting to recent data."
            )
        elif back_positive > forward_positive * 2:
            insights.append(
                f"Back test results much better than forward test. "
                f"Strategy may not adapt well to changing markets."
            )

    return insights


def format_pass_table(passes: list[dict], top_n: int = 20) -> str:
    """Format passes as a readable table."""
    if not passes:
        return "No valid passes found."

    lines = []
    header = (
        f"{'#':<4} {'Trades':<7} {'Profit':>10} {'PF':>6} {'DD%':>6} "
        f"{'Sharpe':>7} {'Fwd':>7} {'Back':>7} {'Score':>6}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for i, p in enumerate(passes[:top_n], 1):
        fwd = p.get('forward_result', 0)
        back = p.get('back_result', 0)
        lines.append(
            f"{i:<4} {p['total_trades']:<7} £{p['profit']:>9,.0f} "
            f"{p['profit_factor']:>6.2f} {p['max_drawdown_pct']:>5.1f}% "
            f"{p['sharpe_ratio']:>7.1f} {fwd:>7.1f} {back:>7.1f} "
            f"{p['composite_score']:>6.1f}"
        )

    return '\n'.join(lines)


def get_pass_details(p: dict) -> str:
    """Get detailed info for a single pass."""
    params = p.get('params', {})

    lines = [
        f"Pass #{params.get('Pass', '?')} Details",
        "=" * 40,
        "",
        "Performance:",
        f"  Profit:        £{p.get('profit', 0):,.2f}",
        f"  Profit Factor: {p.get('profit_factor', 0):.2f}",
        f"  Sharpe Ratio:  {p.get('sharpe_ratio', 0):.2f}",
        f"  Recovery:      {p.get('recovery_factor', 0):.2f}",
        f"  Max Drawdown:  {p.get('max_drawdown_pct', 0):.2f}%",
        f"  Total Trades:  {p.get('total_trades', 0)}",
        f"  Expected Payoff: £{p.get('expected_payoff', 0):.2f}",
        "",
        "Forward/Back Test:",
        f"  Forward Result: {p.get('forward_result', 0):.2f}",
        f"  Back Result:    {p.get('back_result', 0):.2f}",
        f"  Consistent:     {'YES' if p.get('is_consistent') else 'NO'}",
        "",
        "Parameters:",
    ]

    # Filter out metadata params
    skip_params = {'Pass', 'Forward Result', 'Back Result', 'Custom'}
    for name, value in params.items():
        if name not in skip_params:
            lines.append(f"  {name}: {value}")

    return '\n'.join(lines)


def analyze_workflow_results(workflow_path: str) -> dict:
    """Load and analyze optimization results from workflow state."""
    with open(workflow_path, 'r') as f:
        state = json.load(f)

    # Get optimization step results - check multiple possible step names
    steps = state.get('steps', {})
    opt_step = (
        steps.get('7_run_optimization', {}) or
        steps.get('7_optimization', {}) or
        steps.get('optimization', {})
    )
    opt_result = opt_step.get('result', {})
    all_results = opt_result.get('results', [])

    if not all_results:
        return {
            'error': 'No optimization results found in workflow state',
            'insights': ['Run optimization first to generate passes.'],
            'total_passes': 0,
            'filtered_passes': [],
            'rejected_passes': {},
            'valid_count': 0,
        }

    return analyze_passes(all_results)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python pass_analyzer.py <workflow_json>")
        sys.exit(1)

    result = analyze_workflow_results(sys.argv[1])

    print("\n" + "=" * 60)
    print("OPTIMIZATION PASS ANALYSIS")
    print("=" * 60 + "\n")

    print("INSIGHTS:")
    for insight in result['insights']:
        print(f"  • {insight}")

    print("\n" + "-" * 60)
    print("TOP VALID PASSES:")
    print("-" * 60)
    print(format_pass_table(result['filtered_passes']))

    if result['best_consistent']:
        print("\n" + "-" * 60)
        print("RECOMMENDED (Best Consistent):")
        print("-" * 60)
        print(get_pass_details(result['best_consistent']))
