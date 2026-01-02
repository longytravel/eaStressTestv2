"""
Dashboard Generator

Generates HTML dashboard from StatsReport data.
Uses simple string templating - no external dependencies.
"""
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
import re

from .stats_schema import StatsReport, create_sample_report


TEMPLATES_DIR = Path(__file__).parent / 'templates'


def generate_dashboard(
    report: StatsReport,
    output_dir: Optional[str] = None,
    open_browser: bool = False,
) -> str:
    """
    Generate HTML dashboard from StatsReport.

    Args:
        report: StatsReport instance with all data
        output_dir: Where to save files (default: runs/dashboards/{workflow_id}/)
        open_browser: Open in default browser after generation

    Returns:
        Path to generated index.html
    """
    # Determine output directory
    if output_dir is None:
        output_dir = Path('runs/dashboards') / report.workflow_id
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy CSS
    shutil.copy(TEMPLATES_DIR / 'styles.css', output_dir / 'styles.css')

    # Read template
    template = (TEMPLATES_DIR / 'dashboard.html').read_text(encoding='utf-8')

    # Build template context
    ctx = build_context(report)

    # Render template
    html = render_template(template, ctx)

    # Write output
    output_path = output_dir / 'index.html'
    output_path.write_text(html, encoding='utf-8')

    if open_browser:
        import webbrowser
        webbrowser.open(f'file://{output_path.absolute()}')

    return str(output_path)


def build_context(report: StatsReport) -> dict:
    """Build template context from StatsReport."""
    ctx = {}

    # Basic info
    ctx['ea_name'] = report.ea_name
    ctx['symbol'] = report.symbol
    ctx['timeframe'] = report.timeframe
    ctx['terminal'] = report.terminal
    ctx['period_start'] = report.period_start
    ctx['period_end'] = report.period_end
    ctx['workflow_id'] = report.workflow_id
    ctx['generated_at'] = report.generated_at or datetime.now().strftime('%Y-%m-%d %H:%M')

    # Score and status
    ctx['composite_score'] = report.composite_score
    ctx['status'] = report.status

    status_labels = {
        'ready': 'Go-Live Ready',
        'review': 'Needs Review',
        'failed': 'Failed',
        'overfit_risk': 'Overfit Risk',
    }
    ctx['status_label'] = status_labels.get(report.status, report.status.title())

    # Insights
    ctx['edge_summary'] = report.edge_summary
    ctx['weaknesses'] = report.weaknesses
    ctx['recommendations'] = report.recommendations

    # Metrics
    ctx['metrics'] = {
        'profit': f"{report.metrics.profit:,.0f}",
        'profit_factor': f"{report.metrics.profit_factor:.2f}",
        'max_drawdown_pct': f"{report.metrics.max_drawdown_pct:.1f}",
        'total_trades': report.metrics.total_trades,
        'win_rate': f"{report.metrics.win_rate:.0f}",
        'sharpe_ratio': f"{report.metrics.sharpe_ratio:.2f}",
        'sortino_ratio': f"{report.metrics.sortino_ratio:.2f}",
        'calmar_ratio': f"{report.metrics.calmar_ratio:.2f}",
        'expected_payoff': f"{report.metrics.expected_payoff:.1f}",
        'recovery_factor': f"{report.metrics.recovery_factor:.1f}",
    }

    # Gate statuses for metrics
    pf_passed = report.metrics.profit_factor >= 1.5
    ctx['pf_status'] = '≥ 1.5' if pf_passed else '< 1.5'
    ctx['pf_status_class'] = 'metric-pass' if pf_passed else 'metric-fail'

    dd_passed = report.metrics.max_drawdown_pct <= 30
    ctx['dd_status'] = '≤ 30%' if dd_passed else '> 30%'
    ctx['dd_status_class'] = 'metric-pass' if dd_passed else 'metric-fail'

    # Gates list
    ctx['gates_list'] = []
    for name, gate in report.gates.items():
        ctx['gates_list'].append({
            'name': gate.name,
            'value': f"{gate.value:.2f}" if isinstance(gate.value, float) else str(gate.value),
            'threshold': f"{gate.threshold:.2f}" if isinstance(gate.threshold, float) else str(gate.threshold),
            'operator': gate.operator,
            'gate_class': 'gate-pass' if gate.passed else 'gate-fail',
            'gate_icon': '✓' if gate.passed else '✗',
        })

    # Monte Carlo
    ctx['monte_carlo'] = {
        'confidence': f"{report.monte_carlo.confidence:.1f}",
        'ruin_probability': f"{report.monte_carlo.ruin_probability:.1f}",
        'median_profit': f"{report.monte_carlo.median_profit:,.0f}",
        'worst_case_5pct': f"{report.monte_carlo.worst_case_5pct:,.0f}",
        'best_case_95pct': f"{report.monte_carlo.best_case_95pct:,.0f}",
    }

    # Equity curve data for chart
    ctx['equity_dates_json'] = json.dumps(report.equity_curve.dates)
    ctx['equity_values_json'] = json.dumps(report.equity_curve.values)
    ctx['in_sample_end_index'] = report.equity_curve.in_sample_end_index

    # Trade patterns - hourly heatmap
    max_hourly = max(report.trade_patterns.hourly_distribution) if report.trade_patterns.hourly_distribution else 1
    ctx['hourly_heatmap'] = []
    for hour, count in enumerate(report.trade_patterns.hourly_distribution):
        level = min(4, int((count / max(max_hourly, 1)) * 4))
        ctx['hourly_heatmap'].append({
            'hour': hour,
            'count': count,
            'level': level,
        })

    # Trade patterns - daily heatmap
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    max_daily = max(report.trade_patterns.daily_distribution) if report.trade_patterns.daily_distribution else 1
    ctx['daily_heatmap'] = []
    for i, count in enumerate(report.trade_patterns.daily_distribution):
        level = min(4, int((count / max(max_daily, 1)) * 4))
        ctx['daily_heatmap'].append({
            'day': days[i],
            'abbrev': days[i][0],
            'count': count,
            'level': level,
        })

    ctx['trade_patterns'] = {
        'style': report.trade_patterns.style.replace('_', ' ').title(),
        'best_hour': report.trade_patterns.best_hour,
        'best_day': report.trade_patterns.best_day,
    }

    # Holding time display
    mins = report.trade_patterns.holding_time_avg_minutes
    if mins < 60:
        ctx['holding_time_display'] = f"{mins:.0f}m"
    elif mins < 1440:
        ctx['holding_time_display'] = f"{mins/60:.1f}h"
    else:
        ctx['holding_time_display'] = f"{mins/1440:.1f}d"

    # Market regime
    ctx['market_regime'] = {
        'trending': {
            'win_rate': f"{report.market_regime.trending.win_rate:.0f}",
            'profit': f"{report.market_regime.trending.profit:,.0f}",
        },
        'ranging': {
            'win_rate': f"{report.market_regime.ranging.win_rate:.0f}",
            'profit': f"{report.market_regime.ranging.profit:,.0f}",
        },
        'insight': report.market_regime.insight,
    }

    # Calculate widths for regime bars
    total_wr = report.market_regime.trending.win_rate + report.market_regime.ranging.win_rate
    if total_wr > 0:
        ctx['trending_winrate_width'] = (report.market_regime.trending.win_rate / total_wr) * 100
        ctx['ranging_winrate_width'] = (report.market_regime.ranging.win_rate / total_wr) * 100
    else:
        ctx['trending_winrate_width'] = 50
        ctx['ranging_winrate_width'] = 50

    total_profit = abs(report.market_regime.trending.profit) + abs(report.market_regime.ranging.profit)
    if total_profit > 0:
        ctx['trending_profit_width'] = (abs(report.market_regime.trending.profit) / total_profit) * 100
        ctx['ranging_profit_width'] = (abs(report.market_regime.ranging.profit) / total_profit) * 100
    else:
        ctx['trending_profit_width'] = 50
        ctx['ranging_profit_width'] = 50

    # Parameter stability
    ctx['param_stability'] = []
    for param in report.param_stability:
        ctx['param_stability'].append({
            'name': param.name,
            'stable': param.stable,
            'score': param.score,
            'score_pct': param.score * 100,
            'score_display': f"{param.score:.0%}",
            'stability_class': 'param-stable' if param.stable else 'param-fragile',
            'warning': param.warning if not param.stable else '',
        })

    # Diagnosis
    ctx['has_diagnosis'] = len(report.diagnosis.failed_gates) > 0
    ctx['diagnosis_severity'] = 'critical' if len(report.diagnosis.failed_gates) > 2 else ''
    ctx['diagnosis_reasons'] = [
        {'gate': g, 'reason': r}
        for g, r in zip(report.diagnosis.failed_gates, report.diagnosis.reasons)
    ]
    ctx['diagnosis_fixes'] = report.diagnosis.fixes

    # Top passes (placeholder - would come from optimization results)
    ctx['has_top_passes'] = False
    ctx['top_passes'] = []

    return ctx


def render_template(template: str, ctx: dict) -> str:
    """
    Simple mustache-like template rendering.

    Supports:
    - {{variable}} - simple substitution
    - {{object.property}} - nested access
    - {{#list}}...{{/list}} - iteration
    - {{^list}}...{{/list}} - inverted (if empty)
    - {{#bool}}...{{/bool}} - conditional
    """
    result = template

    # Handle nested object access like {{metrics.profit}}
    def replace_nested(match):
        keys = match.group(1).split('.')
        value = ctx
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, '')
            else:
                return ''
        return str(value) if value is not None else ''

    result = re.sub(r'\{\{([a-zA-Z_][a-zA-Z0-9_.]*)\}\}', replace_nested, result)

    # Handle sections (lists and conditionals)
    # This is simplified - for complex templates, use a proper library

    # {{#list}}...{{/list}} - iteration over lists
    section_pattern = r'\{\{#([a-zA-Z_][a-zA-Z0-9_]*)\}\}(.*?)\{\{/\1\}\}'

    def replace_section(match):
        key = match.group(1)
        content = match.group(2)
        value = ctx.get(key)

        if value is None:
            return ''

        if isinstance(value, list):
            # Iterate over list
            result_parts = []
            for item in value:
                item_content = content
                if isinstance(item, dict):
                    # Replace {{.property}} with item.property
                    for k, v in item.items():
                        item_content = item_content.replace(f'{{{{{k}}}}}', str(v) if v else '')
                        # Handle {{#key}} conditionals within item
                        if v:
                            item_content = re.sub(
                                rf'\{{\{{#{k}\}}\}}(.*?)\{{\{{/{k}\}}\}}',
                                r'\1',
                                item_content,
                                flags=re.DOTALL
                            )
                        else:
                            item_content = re.sub(
                                rf'\{{\{{#{k}\}}\}}.*?\{{\{{/{k}\}}\}}',
                                '',
                                item_content,
                                flags=re.DOTALL
                            )
                else:
                    # Simple list - replace {{.}} with item
                    item_content = item_content.replace('{{.}}', str(item))
                result_parts.append(item_content)
            return ''.join(result_parts)

        elif isinstance(value, bool):
            # Conditional
            return content if value else ''

        elif value:
            # Truthy value
            return content

        return ''

    # Apply section replacements (may need multiple passes for nested)
    for _ in range(3):
        result = re.sub(section_pattern, replace_section, result, flags=re.DOTALL)

    # Handle inverted sections {{^key}}...{{/key}}
    inverted_pattern = r'\{\{\^([a-zA-Z_][a-zA-Z0-9_]*)\}\}(.*?)\{\{/\1\}\}'

    def replace_inverted(match):
        key = match.group(1)
        content = match.group(2)
        value = ctx.get(key)

        # Show content if value is falsy or empty list
        if not value or (isinstance(value, list) and len(value) == 0):
            return content
        return ''

    result = re.sub(inverted_pattern, replace_inverted, result, flags=re.DOTALL)

    return result


def generate_sample_dashboard(output_dir: Optional[str] = None) -> str:
    """Generate a dashboard with sample data for testing."""
    report = create_sample_report()
    return generate_dashboard(report, output_dir, open_browser=True)


if __name__ == '__main__':
    # Test with sample data
    path = generate_sample_dashboard()
    print(f"Dashboard generated: {path}")
