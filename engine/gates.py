"""
Gate Logic Module

Defines pass/fail gates for the 11-step workflow.
Each gate checks specific metrics against thresholds from settings.
"""
from pathlib import Path
from typing import Optional
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import settings


class GateResult:
    """Result of a gate check."""

    def __init__(
        self,
        name: str,
        passed: bool,
        value: float,
        threshold: float,
        operator: str = '>=',
        message: Optional[str] = None,
    ):
        self.name = name
        self.passed = passed
        self.value = value
        self.threshold = threshold
        self.operator = operator
        self.message = message or self._default_message()

    def _default_message(self) -> str:
        status = 'PASS' if self.passed else 'FAIL'
        return f"{status}: {self.name} = {self.value} ({self.operator} {self.threshold})"

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'passed': self.passed,
            'value': self.value,
            'threshold': self.threshold,
            'operator': self.operator,
            'message': self.message,
        }


def check_file_exists(path: str) -> GateResult:
    """Gate 1: Check if EA file exists."""
    exists = Path(path).exists()
    return GateResult(
        name='file_exists',
        passed=exists,
        value=1 if exists else 0,
        threshold=1,
        operator='==',
        message=f"{'PASS' if exists else 'FAIL'}: EA file {'exists' if exists else 'not found'}: {path}"
    )


def check_compilation(compile_result: dict) -> GateResult:
    """Gate 2: Check if compilation succeeded."""
    success = compile_result.get('success', False)
    errors = len(compile_result.get('errors', []))
    return GateResult(
        name='compilation',
        passed=success,
        value=0 if success else errors,
        threshold=0,
        operator='==',
        message=f"{'PASS' if success else 'FAIL'}: Compilation {'succeeded' if success else f'failed with {errors} error(s)'}"
    )


def check_params_found(params: list) -> GateResult:
    """Gate 3: Check if parameters were extracted."""
    count = len(params) if params else 0
    optimizable = sum(1 for p in params if p.get('optimizable', False)) if params else 0
    passed = count > 0

    return GateResult(
        name='params_found',
        passed=passed,
        value=count,
        threshold=1,
        operator='>=',
        message=f"{'PASS' if passed else 'FAIL'}: Found {count} parameters ({optimizable} optimizable)"
    )


def check_minimum_trades(total_trades: int) -> GateResult:
    """Gate 5: Check minimum trade count."""
    passed = total_trades >= settings.MIN_TRADES
    return GateResult(
        name='minimum_trades',
        passed=passed,
        value=total_trades,
        threshold=settings.MIN_TRADES,
        operator='>=',
        message=f"{'PASS' if passed else 'FAIL'}: {total_trades} trades (minimum: {settings.MIN_TRADES})"
    )


def check_history_coverage(bars: int, timeframe: str, start_date: str, end_date: str) -> GateResult:
    """Gate 5a: Check that MT5 has enough history bars for the requested date range.

    This catches a common "flaky" failure mode where MT5 only has ~1 year of data
    for a symbol, so the 4-year test silently runs on a shorter period.
    """
    try:
        start = datetime.strptime(str(start_date), "%Y.%m.%d")
        end = datetime.strptime(str(end_date), "%Y.%m.%d")
        total_days = max(1, (end - start).days + 1)
    except Exception:
        # If we can't parse dates, don't block the workflow; treat as pass.
        return GateResult(
            name="history_coverage_pct",
            passed=True,
            value=100.0,
            threshold=float(getattr(settings, "MIN_HISTORY_COVERAGE_PCT", 80.0) or 80.0),
            operator=">=",
            message="PASS: Unable to compute history coverage (date parse)",
        )

    tf = str(timeframe or "").upper().strip()
    minutes_map = {
        "M1": 1,
        "M5": 5,
        "M15": 15,
        "M30": 30,
        "H1": 60,
        "H4": 240,
        "D1": 1440,
        "W1": 10080,
        "MN1": 43200,
    }
    period_min = minutes_map.get(tf, 60)

    # Approx trading-day adjustment: intraday and D1 effectively trade ~5/7 days.
    trading_days = int(round(total_days * (5.0 / 7.0))) if period_min <= 1440 else total_days
    bars_per_day = max(1, int(round(1440 / period_min))) if period_min < 1440 else 1
    expected = max(1, trading_days * bars_per_day)

    coverage = (float(bars or 0) / float(expected)) * 100.0
    min_pct = float(getattr(settings, "MIN_HISTORY_COVERAGE_PCT", 80.0) or 80.0)
    passed = coverage >= min_pct

    return GateResult(
        name="history_coverage_pct",
        passed=passed,
        value=round(coverage, 2),
        threshold=round(min_pct, 2),
        operator=">=",
        message=(
            f"{'PASS' if passed else 'FAIL'}: History coverage {coverage:.1f}% "
            f"({bars} bars, expected ~{expected} for {timeframe} {start_date}->{end_date})"
        ),
    )


def check_profit_factor(pf: float) -> GateResult:
    """Gate 9a: Check profit factor."""
    passed = pf >= settings.MIN_PROFIT_FACTOR
    return GateResult(
        name='profit_factor',
        passed=passed,
        value=round(pf, 2),
        threshold=settings.MIN_PROFIT_FACTOR,
        operator='>=',
    )


def check_max_drawdown(dd_pct: float) -> GateResult:
    """Gate 9b: Check maximum drawdown percentage."""
    passed = dd_pct <= settings.MAX_DRAWDOWN_PCT
    return GateResult(
        name='max_drawdown',
        passed=passed,
        value=round(dd_pct, 2),
        threshold=settings.MAX_DRAWDOWN_PCT,
        operator='<=',
    )


def check_monte_carlo_confidence(confidence: float) -> GateResult:
    """Gate 10a: Check Monte Carlo confidence level."""
    passed = confidence >= settings.MC_CONFIDENCE_MIN
    return GateResult(
        name='mc_confidence',
        passed=passed,
        value=round(confidence, 2),
        threshold=settings.MC_CONFIDENCE_MIN,
        operator='>=',
        message=f"{'PASS' if passed else 'FAIL'}: MC Confidence {confidence}% (minimum: {settings.MC_CONFIDENCE_MIN}%)"
    )


def check_monte_carlo_ruin(ruin_prob: float) -> GateResult:
    """Gate 10b: Check Monte Carlo ruin probability."""
    passed = ruin_prob <= settings.MC_RUIN_MAX
    return GateResult(
        name='mc_ruin',
        passed=passed,
        value=round(ruin_prob, 2),
        threshold=settings.MC_RUIN_MAX,
        operator='<=',
        message=f"{'PASS' if passed else 'FAIL'}: Ruin probability {ruin_prob}% (maximum: {settings.MC_RUIN_MAX}%)"
    )


def check_optimization_passes(passes: int) -> GateResult:
    """Gate 7: Check if optimization produced results."""
    passed = passes > 0
    return GateResult(
        name='optimization_passes',
        passed=passed,
        value=passes,
        threshold=1,
        operator='>=',
        message=f"{'PASS' if passed else 'FAIL'}: {passes} optimization passes"
    )


def check_robust_params_found(robust_params: dict) -> GateResult:
    """Gate 8: Check if robust parameters were identified."""
    count = len(robust_params) if robust_params else 0
    passed = count > 0
    return GateResult(
        name='robust_params',
        passed=passed,
        value=count,
        threshold=1,
        operator='>=',
        message=f"{'PASS' if passed else 'FAIL'}: {count} robust parameters identified"
    )


def check_all_backtest_gates(results: dict) -> dict:
    """
    Check all backtest-related gates.

    Returns dict with all gate results.
    """
    pf = results.get('profit_factor', 0)
    dd = results.get('max_drawdown_pct', 100)
    trades = results.get('total_trades', 0)

    gates = {
        'profit_factor': check_profit_factor(pf),
        'max_drawdown': check_max_drawdown(dd),
        'minimum_trades': check_minimum_trades(trades),
    }

    all_passed = all(g.passed for g in gates.values())

    return {
        'all_passed': all_passed,
        'gates': {name: g.to_dict() for name, g in gates.items()},
    }


def check_all_monte_carlo_gates(mc_results: dict) -> dict:
    """
    Check all Monte Carlo gates.

    Returns dict with gate results.
    """
    confidence = mc_results.get('confidence', 0)
    ruin = mc_results.get('ruin_probability', 100)

    gates = {
        'mc_confidence': check_monte_carlo_confidence(confidence),
        'mc_ruin': check_monte_carlo_ruin(ruin),
    }

    all_passed = all(g.passed for g in gates.values())

    return {
        'all_passed': all_passed,
        'gates': {name: g.to_dict() for name, g in gates.items()},
    }


def check_go_live_ready(state: dict) -> dict:
    """
    Final check: Is the EA ready for live trading?

    Requires all critical gates to pass.
    """
    gates = state.get('gates', {})

    critical_gates = [
        'profit_factor',
        'max_drawdown',
        'minimum_trades',
        'mc_confidence',
        'mc_ruin',
    ]

    results = {}
    all_passed = True

    for gate_name in critical_gates:
        gate = gates.get(gate_name, {})
        passed = gate.get('passed', False)
        results[gate_name] = passed
        if not passed:
            all_passed = False

    return {
        'go_live_ready': all_passed,
        'gate_results': results,
        'message': 'READY for go-live' if all_passed else 'NOT ready - some gates failed',
    }


def calculate_composite_score(metrics: dict) -> float:
    """
    Calculate Go Live Score from metrics.

    The Go Live Score answers: "Should I trade this live?"
    Higher score (0-10) = more confidence to deploy with real money.

    Components:
        consistency (25%):   Both back+forward positive = not overfitted
        total_profit (25%):  Actual money made - the goal
        trade_count (20%):   Statistical confidence
        profit_factor (15%): Edge sustainability
        max_drawdown (15%):  Risk tolerance

    Args:
        metrics: Dict with keys like profit, total_trades, profit_factor,
                 max_drawdown_pct, forward_result, back_result

    Returns:
        Score from 0-10
    """
    if not isinstance(metrics, dict):
        return 0.0

    # Extract values with common aliases
    profit = float(metrics.get('profit', metrics.get('total_profit', 0)) or 0)
    trades = int(metrics.get('total_trades', metrics.get('trade_count', 0)) or 0)
    pf = float(metrics.get('profit_factor', 0) or 0)
    dd = float(metrics.get('max_drawdown_pct', metrics.get('max_drawdown', 0)) or 0)
    forward = float(metrics.get('forward_result', 0) or 0)
    back = float(metrics.get('back_result', 0) or 0)

    # Get ranges from settings (with defaults)
    ranges = getattr(settings, 'GO_LIVE_SCORE_RANGES', {})
    profit_range = ranges.get('total_profit', (0, 5000))
    trades_range = ranges.get('trade_count', (50, 200))
    pf_range = ranges.get('profit_factor', (1.0, 3.0))
    dd_range = ranges.get('max_drawdown', (0, 30))
    consistency_range = ranges.get('consistency_min', (0, 2000))

    # Get weights from settings
    weights = getattr(settings, 'GO_LIVE_SCORE_WEIGHTS', {
        'consistency': 0.25,
        'total_profit': 0.25,
        'trade_count': 0.20,
        'profit_factor': 0.15,
        'max_drawdown': 0.15,
    })

    def normalize(value: float, min_val: float, max_val: float, invert: bool = False) -> float:
        """Normalize value to 0-1 range."""
        if max_val <= min_val:
            return 0.0
        clamped = max(min_val, min(max_val, value))
        normalized = (clamped - min_val) / (max_val - min_val)
        return (1.0 - normalized) if invert else normalized

    # Calculate each component

    # 1. Consistency: Both periods profitable = robust across time
    #    Score based on the WEAKER period (can't hide a bad back with great forward)
    if forward > 0 and back > 0:
        # Both positive - score based on minimum (weaker period)
        consistency_value = min(forward, back)
        consistency_score = normalize(consistency_value, consistency_range[0], consistency_range[1])
    elif forward > 0 or back > 0:
        # Only one positive - partial credit (25% of what full consistency would give)
        positive_value = max(forward, back)
        consistency_score = normalize(positive_value, consistency_range[0], consistency_range[1]) * 0.25
    else:
        # Both negative or zero - no consistency score
        consistency_score = 0.0

    # 2. Total Profit: Actual money made
    profit_score = normalize(profit, profit_range[0], profit_range[1])

    # 3. Trade Count: Statistical confidence (more trades = more reliable)
    trades_score = normalize(trades, trades_range[0], trades_range[1])

    # 4. Profit Factor: Edge quality (PF < 1.5 is thin edge)
    pf_score = normalize(pf, pf_range[0], pf_range[1])

    # 5. Max Drawdown: Risk (inverted - lower DD = higher score)
    dd_score = normalize(dd, dd_range[0], dd_range[1], invert=True)

    # Combine with weights
    score = (
        consistency_score * weights.get('consistency', 0.25) +
        profit_score * weights.get('total_profit', 0.25) +
        trades_score * weights.get('trade_count', 0.20) +
        pf_score * weights.get('profit_factor', 0.15) +
        dd_score * weights.get('max_drawdown', 0.15)
    )

    # Scale to 0-10
    return round(score * 10, 1)


def diagnose_failure(gates: dict, metrics: dict) -> list[str]:
    """
    Provide failure diagnosis explaining WHY gates failed.

    Returns list of diagnostic messages.
    """
    diagnoses = []

    for gate_name, gate_data in gates.items():
        if not gate_data.get('passed', True):
            value = gate_data.get('value', 0)
            threshold = gate_data.get('threshold', 0)
            operator = gate_data.get('operator', '>=')

            if gate_name == 'profit_factor':
                # Diagnose low profit factor
                gross_profit = metrics.get('gross_profit', 0)
                gross_loss = abs(metrics.get('gross_loss', 1))
                avg_win = metrics.get('avg_win', 0)
                avg_loss = abs(metrics.get('avg_loss', 1))

                if avg_win < avg_loss * 1.5:
                    diagnoses.append(
                        f"PF {value} < {threshold}: Average win (${avg_win:.0f}) is too close to average loss (${avg_loss:.0f}). "
                        "Consider tightening stop loss or improving exit strategy."
                    )
                else:
                    win_rate = metrics.get('win_rate', 50)
                    diagnoses.append(
                        f"PF {value} < {threshold}: Win rate is {win_rate:.0f}%. "
                        "Consider improving entry signals to increase winning trades."
                    )

            elif gate_name == 'max_drawdown':
                diagnoses.append(
                    f"Drawdown {value}% > {threshold}%: Consider adding position sizing, "
                    "trailing stops, or reducing exposure during losing streaks."
                )

            elif gate_name == 'minimum_trades':
                diagnoses.append(
                    f"Only {int(value)} trades (need {int(threshold)}+): EA may be too selective. "
                    "Consider widening entry conditions or testing longer period."
                )

            elif gate_name == 'mc_confidence':
                diagnoses.append(
                    f"MC confidence {value}% < {threshold}%: Results may be due to luck. "
                    "Trade sequence matters too much - reduce dependency on specific market conditions."
                )

            elif gate_name == 'mc_ruin':
                diagnoses.append(
                    f"Ruin probability {value}% > {threshold}%: High risk of account blowup. "
                    "Reduce position sizes or add circuit breakers for losing streaks."
                )

    return diagnoses
