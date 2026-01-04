"""
Gate Logic Module

Defines pass/fail gates for the 11-step workflow.
Each gate checks specific metrics against thresholds from settings.
"""
from pathlib import Path
from typing import Optional
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
    Calculate composite score from metrics using weighted formula.

    Returns score from 0-10.
    """
    # Accept common aliases used elsewhere in the codebase/state files.
    # (Workflow state stores drawdown as `max_drawdown_pct` but scoring expects `max_drawdown`.)
    if isinstance(metrics, dict):
        if 'max_drawdown' not in metrics and 'max_drawdown_pct' in metrics:
            metrics = {**metrics, 'max_drawdown': metrics.get('max_drawdown_pct', 0)}

    weights = settings.SCORE_WEIGHTS
    score = 0
    total_weight = 0

    # Normalize each metric to 0-1 scale, then apply weight
    normalizers = {
        'profit_factor': lambda x: min(1, (x - 1) / 2) if x > 1 else 0,  # 1-3 -> 0-1
        'max_drawdown': lambda x: max(0, 1 - x / 50),  # 0-50% -> 1-0
        'sharpe_ratio': lambda x: min(1, x / 3) if x > 0 else 0,  # 0-3 -> 0-1
        'sortino_ratio': lambda x: min(1, x / 4) if x > 0 else 0,  # 0-4 -> 0-1
        'calmar_ratio': lambda x: min(1, x / 5) if x > 0 else 0,  # 0-5 -> 0-1
        'recovery_factor': lambda x: min(1, x / 5) if x > 0 else 0,  # 0-5 -> 0-1
        'expected_payoff': lambda x: min(1, x / 50) if x > 0 else 0,  # 0-50 -> 0-1
        'win_rate': lambda x: min(1, (x - 30) / 40) if x > 30 else 0,  # 30-70% -> 0-1
        'param_stability': lambda x: x,  # Already 0-1
    }

    for metric_name, weight in weights.items():
        value = metrics.get(metric_name, 0)
        normalizer = normalizers.get(metric_name, lambda x: min(1, x))

        try:
            normalized = normalizer(float(value))
            score += normalized * weight
            total_weight += weight
        except (ValueError, TypeError):
            pass

    # Scale to 0-10
    if total_weight > 0:
        score = (score / total_weight) * 10

    return round(score, 1)


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
