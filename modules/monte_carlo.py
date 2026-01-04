"""
Monte Carlo Simulation Module

Performs Monte Carlo analysis on trading results to assess robustness.
Shuffles trade sequence to estimate probability of ruin and confidence intervals.
"""
import random
from typing import Optional
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import settings


def run_monte_carlo(
    trades: list[float],
    initial_balance: float = 10000,
    iterations: int = None,
    ruin_threshold: float = 0.5,  # 50% drawdown = ruin
    confidence_levels: list[float] = None,
) -> dict:
    """
    Run Monte Carlo simulation on trade results.

    Args:
        trades: List of trade profits/losses
        initial_balance: Starting account balance
        iterations: Number of simulation iterations
        ruin_threshold: Drawdown level considered as ruin (0.5 = 50%)
        confidence_levels: Percentiles to calculate (e.g., [0.05, 0.25, 0.50, 0.75, 0.95])

    Returns:
        dict with:
            - success: bool
            - iterations: int
            - ruin_probability: float (0-100%)
            - confidence: float (probability of profit, 0-100%)
            - expected_profit: float
            - median_profit: float
            - worst_case: float (5th percentile)
            - best_case: float (95th percentile)
            - max_drawdown_median: float
            - max_drawdown_worst: float (95th percentile of drawdowns)
            - percentiles: dict of level -> profit value
            - drawdown_percentiles: dict of level -> max drawdown (%)
            - distribution: list of final profits (for charting)
            - drawdown_distribution: list of max drawdowns (%) (for charting)
            - passed_gates: bool
            - errors: list
    """
    if not trades:
        return {
            'success': False,
            'errors': ['No trades provided for simulation'],
        }

    if iterations is None:
        iterations = settings.MC_ITERATIONS

    if confidence_levels is None:
        confidence_levels = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]

    # Run simulations
    final_profits = []
    max_drawdowns = []
    ruin_count = 0

    for _ in range(iterations):
        # Shuffle trade order
        shuffled = trades.copy()
        random.shuffle(shuffled)

        # Simulate equity curve
        balance = initial_balance
        peak = initial_balance
        max_dd = 0
        ruined = False

        for trade in shuffled:
            balance += trade
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
            if dd >= ruin_threshold:
                ruined = True

        final_profits.append(balance - initial_balance)
        max_drawdowns.append(max_dd * 100)  # As percentage

        if ruined:
            ruin_count += 1

    # Calculate statistics
    final_profits.sort()
    max_drawdowns.sort()

    n = len(final_profits)

    # Percentiles
    percentiles = {}
    for level in confidence_levels:
        idx = int(level * n)
        idx = max(0, min(idx, n - 1))
        percentiles[level] = final_profits[idx]

    # Drawdown percentiles
    drawdown_percentiles = {}
    for level in confidence_levels:
        idx = int(level * n)
        idx = max(0, min(idx, n - 1))
        drawdown_percentiles[level] = max_drawdowns[idx]

    # Core metrics
    ruin_probability = (ruin_count / iterations) * 100
    profitable_count = sum(1 for p in final_profits if p > 0)
    confidence = (profitable_count / iterations) * 100

    expected_profit = sum(final_profits) / n
    median_profit = final_profits[n // 2]

    worst_case = percentiles.get(0.05, final_profits[0])
    best_case = percentiles.get(0.95, final_profits[-1])

    # Drawdown stats
    dd_median = max_drawdowns[n // 2]
    dd_worst = max_drawdowns[int(0.95 * n)]

    # Check gates
    passed_gates = (
        ruin_probability <= settings.MC_RUIN_MAX and
        confidence >= settings.MC_CONFIDENCE_MIN
    )

    return {
        'success': True,
        'iterations': iterations,
        'ruin_probability': round(ruin_probability, 2),
        'confidence': round(confidence, 2),
        'expected_profit': round(expected_profit, 2),
        'median_profit': round(median_profit, 2),
        'worst_case': round(worst_case, 2),
        'best_case': round(best_case, 2),
        'max_drawdown_median': round(dd_median, 2),
        'max_drawdown_worst': round(dd_worst, 2),
        'percentiles': {k: round(v, 2) for k, v in percentiles.items()},
        'drawdown_percentiles': {k: round(v, 2) for k, v in drawdown_percentiles.items()},
        'distribution': final_profits,  # For histogram
        'drawdown_distribution': max_drawdowns,  # For histogram
        'passed_gates': passed_gates,
        'gate_details': {
            'ruin_ok': ruin_probability <= settings.MC_RUIN_MAX,
            'ruin_threshold': settings.MC_RUIN_MAX,
            'confidence_ok': confidence >= settings.MC_CONFIDENCE_MIN,
            'confidence_threshold': settings.MC_CONFIDENCE_MIN,
        },
        'errors': [],
    }


def extract_trades_from_results(backtest_results: dict) -> list[float]:
    """
    Extract individual trade profits from backtest results.

    Note: This requires detailed trade data from the backtest.
    If only summary stats available, we estimate from available data.
    """
    # If we have actual trade list
    if 'trades' in backtest_results:
        return [t.get('profit', 0) for t in backtest_results['trades']]

    # Estimate from summary statistics
    total_trades = backtest_results.get('total_trades', 0)
    if total_trades == 0:
        return []

    profit = backtest_results.get('profit', 0)
    win_rate = backtest_results.get('win_rate', 50) / 100
    gross_profit = backtest_results.get('gross_profit', 0)
    gross_loss = backtest_results.get('gross_loss', 0)

    # Estimate individual trade sizes
    winning_trades = int(total_trades * win_rate)
    losing_trades = total_trades - winning_trades

    avg_win = gross_profit / winning_trades if winning_trades > 0 else 0
    avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0

    # Generate estimated trades
    trades = []
    trades.extend([avg_win] * winning_trades)
    trades.extend([avg_loss] * losing_trades)  # Already negative

    return trades


def calculate_risk_metrics(
    trades: list[float],
    initial_balance: float = 10000,
    risk_free_rate: float = None,
    trading_days_per_year: int = 252,
) -> dict:
    """
    Calculate risk-adjusted performance metrics from trade list.

    Returns:
        dict with Sharpe, Sortino, Calmar ratios and other metrics
    """
    if not trades:
        return {'success': False, 'errors': ['No trades']}

    if risk_free_rate is None:
        risk_free_rate = settings.RISK_FREE_RATE

    # Build equity curve
    equity = [initial_balance]
    for trade in trades:
        equity.append(equity[-1] + trade)

    # Calculate returns
    returns = []
    for i in range(1, len(equity)):
        ret = (equity[i] - equity[i-1]) / equity[i-1] if equity[i-1] != 0 else 0
        returns.append(ret)

    if not returns:
        return {'success': False, 'errors': ['No returns calculated']}

    # Basic stats
    n = len(returns)
    mean_return = sum(returns) / n
    total_return = (equity[-1] - equity[0]) / equity[0]

    # Annualize (assuming daily returns)
    annual_return = mean_return * trading_days_per_year

    # Standard deviation
    variance = sum((r - mean_return) ** 2 for r in returns) / n
    std_dev = variance ** 0.5
    annual_std = std_dev * (trading_days_per_year ** 0.5)

    # Downside deviation (for Sortino)
    # Standard definition uses the total number of periods (n), not the count of downside periods.
    downside_returns = [r for r in returns if r < 0]
    if downside_returns:
        downside_var = sum(r ** 2 for r in downside_returns) / n
        downside_std = downside_var ** 0.5
        annual_downside_std = downside_std * (trading_days_per_year ** 0.5)
    else:
        annual_downside_std = 0.0001  # Avoid division by zero

    # Max drawdown
    peak = equity[0]
    max_dd = 0
    for val in equity:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Sharpe Ratio
    sharpe = (annual_return - risk_free_rate) / annual_std if annual_std > 0 else 0

    # Sortino Ratio
    sortino = (annual_return - risk_free_rate) / annual_downside_std if annual_downside_std > 0 else 0

    # Calmar Ratio
    calmar = annual_return / max_dd if max_dd > 0 else 0

    # Recovery Factor
    max_dd_value = max_dd * initial_balance
    net_profit = equity[-1] - equity[0]
    recovery = net_profit / max_dd_value if max_dd_value > 0 else 0

    return {
        'success': True,
        'sharpe_ratio': round(sharpe, 3),
        'sortino_ratio': round(sortino, 3),
        'calmar_ratio': round(calmar, 3),
        'recovery_factor': round(recovery, 3),
        'total_return_pct': round(total_return * 100, 2),
        'annual_return_pct': round(annual_return * 100, 2),
        'max_drawdown_pct': round(max_dd * 100, 2),
        'volatility_pct': round(annual_std * 100, 2),
        'downside_volatility_pct': round(annual_downside_std * 100, 2),
        'errors': [],
    }


def check_monte_carlo_gates(mc_results: dict) -> dict:
    """
    Check if Monte Carlo results pass the required gates.

    Returns:
        dict with gate check results
    """
    ruin_prob = mc_results.get('ruin_probability', 100)
    confidence = mc_results.get('confidence', 0)

    ruin_ok = ruin_prob <= settings.MC_RUIN_MAX
    conf_ok = confidence >= settings.MC_CONFIDENCE_MIN

    return {
        'passed': ruin_ok and conf_ok,
        'ruin_probability': {
            'value': ruin_prob,
            'threshold': settings.MC_RUIN_MAX,
            'passed': ruin_ok,
            'message': f"{'PASS' if ruin_ok else 'FAIL'}: {ruin_prob}% (max: {settings.MC_RUIN_MAX}%)"
        },
        'confidence': {
            'value': confidence,
            'threshold': settings.MC_CONFIDENCE_MIN,
            'passed': conf_ok,
            'message': f"{'PASS' if conf_ok else 'FAIL'}: {confidence}% (min: {settings.MC_CONFIDENCE_MIN}%)"
        },
    }
