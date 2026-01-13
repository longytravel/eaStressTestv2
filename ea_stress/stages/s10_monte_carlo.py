"""
Stage 10: Monte Carlo Simulation

Run Monte Carlo simulation on best pass from Step 9.
Shuffles trade order to test sequence dependency and estimate ruin probability.
"""

import random
from typing import TYPE_CHECKING, Any

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class MonteCarloStage:
    """Stage 10: Run Monte Carlo simulation on best backtest pass."""

    @property
    def name(self) -> str:
        return "10_monte_carlo"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Execute Monte Carlo simulation on best pass.

        Requires:
            - Step 9 (backtest_passes) completed with best_result

        Args:
            state: Current workflow state
            mt5: Not required for this stage

        Returns:
            StageResult with confidence, ruin probability, and percentiles
        """
        from ea_stress.core.metrics import GateResult

        # Get best result from Step 9
        step_9 = state.steps.get("9_backtest_passes")
        if not step_9 or not step_9.passed or not step_9.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 9 (backtest_passes) must complete successfully first",),
            )

        best_result = step_9.result.get("best_result")
        if not best_result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No best_result from Step 9",),
            )

        # Extract trades from best result
        trades = self._extract_trades(best_result)
        if not trades:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No trades to simulate from best pass",),
            )

        # Import settings
        import settings

        iterations = getattr(settings, "MC_ITERATIONS", 10000)
        initial_balance = getattr(settings, "INITIAL_BALANCE", 10000.0)
        ruin_threshold = 0.5  # 50% drawdown = ruin
        confidence_levels = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]

        # Run simulation
        mc_result = self._run_monte_carlo(
            trades=trades,
            initial_balance=initial_balance,
            iterations=iterations,
            ruin_threshold=ruin_threshold,
            confidence_levels=confidence_levels,
        )

        # Check gates
        mc_confidence_min = getattr(settings, "MC_CONFIDENCE_MIN", 70.0)
        mc_ruin_max = getattr(settings, "MC_RUIN_MAX", 5.0)

        confidence = mc_result["confidence"]
        ruin_prob = mc_result["ruin_probability"]

        gate = GateResult(
            name="mc_confidence",
            passed=confidence >= mc_confidence_min and ruin_prob <= mc_ruin_max,
            value=confidence,
            threshold=mc_confidence_min,
            operator=">=",
        )

        # Add pass info
        mc_result["pass_num"] = best_result.get("pass_num")
        mc_result["trade_count"] = len(trades)

        if gate.passed:
            return StageResult(
                success=True,
                data=mc_result,
                gate=gate,
                errors=(),
            )
        else:
            errors: list[str] = []
            if confidence < mc_confidence_min:
                errors.append(
                    f"MC confidence {confidence:.1f}% < {mc_confidence_min}% minimum"
                )
            if ruin_prob > mc_ruin_max:
                errors.append(
                    f"MC ruin probability {ruin_prob:.1f}% > {mc_ruin_max}% maximum"
                )
            return StageResult(
                success=False,
                data=mc_result,
                gate=gate,
                errors=tuple(errors),
            )

    def _extract_trades(self, backtest_result: dict[str, Any]) -> list[float]:
        """Extract trade profits from backtest result.

        If actual trades available, use them.
        Otherwise estimate from summary statistics.

        Args:
            backtest_result: Best pass backtest result

        Returns:
            List of trade profits (positive for wins, negative for losses)
        """
        # Check for actual trade list
        trades = backtest_result.get("trades")
        if trades and isinstance(trades, list):
            return [
                t.get("profit", 0) if isinstance(t, dict) else float(t)
                for t in trades
            ]

        # Estimate from summary statistics
        total_trades = backtest_result.get("total_trades", 0)
        if total_trades <= 0:
            return []

        win_rate = backtest_result.get("win_rate", 50) / 100.0
        profit = backtest_result.get("profit", 0)

        # Calculate gross profit/loss from profit factor if available
        pf = backtest_result.get("profit_factor", 1.0)

        if pf > 0 and pf != 1.0:
            # profit_factor = gross_profit / abs(gross_loss)
            # profit = gross_profit - abs(gross_loss)
            # Solve: gross_profit = pf * abs(gross_loss)
            #        profit = pf * abs(gross_loss) - abs(gross_loss)
            #        profit = abs(gross_loss) * (pf - 1)
            #        abs(gross_loss) = profit / (pf - 1)
            if pf > 1 and profit > 0:
                gross_loss = -profit / (pf - 1)
                gross_profit = profit - gross_loss
            else:
                # Fallback: distribute profit evenly
                gross_profit = max(profit, 0)
                gross_loss = min(profit, 0)
        else:
            gross_profit = max(profit, 0)
            gross_loss = min(profit, 0)

        winning_trades = int(total_trades * win_rate)
        losing_trades = total_trades - winning_trades

        if winning_trades <= 0:
            winning_trades = 1
        if losing_trades <= 0:
            losing_trades = 1

        avg_win = gross_profit / winning_trades if winning_trades > 0 else 0
        avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0

        # Build trade list
        trade_list: list[float] = []
        trade_list.extend([avg_win] * winning_trades)
        trade_list.extend([avg_loss] * losing_trades)

        return trade_list

    def _run_monte_carlo(
        self,
        trades: list[float],
        initial_balance: float,
        iterations: int,
        ruin_threshold: float,
        confidence_levels: list[float],
    ) -> dict[str, Any]:
        """Run Monte Carlo simulation.

        Shuffles trade order N times and tracks:
        - Final profit for each sequence
        - Maximum drawdown for each sequence
        - Ruin count (hit 50% drawdown)

        Args:
            trades: List of trade profits
            initial_balance: Starting balance
            iterations: Number of shuffle iterations
            ruin_threshold: Drawdown % that defines ruin (0.5 = 50%)
            confidence_levels: Percentiles to calculate

        Returns:
            Dictionary with simulation results
        """
        final_profits: list[float] = []
        max_drawdowns: list[float] = []
        ruin_count = 0

        for _ in range(iterations):
            # Shuffle trade order
            shuffled = trades.copy()
            random.shuffle(shuffled)

            # Simulate equity curve
            balance = initial_balance
            peak = initial_balance
            max_dd = 0.0
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
            max_drawdowns.append(max_dd * 100)  # Store as percentage

            if ruined:
                ruin_count += 1

        # Sort for percentile calculations
        final_profits.sort()
        max_drawdowns.sort()

        n = len(final_profits)

        # Core metrics
        ruin_probability = (ruin_count / iterations) * 100
        profitable_count = sum(1 for p in final_profits if p > 0)
        confidence = (profitable_count / iterations) * 100

        expected_profit = sum(final_profits) / n
        median_profit = final_profits[n // 2]

        # Percentiles
        percentiles: dict[float, float] = {}
        for level in confidence_levels:
            idx = int(level * n)
            idx = max(0, min(n - 1, idx))
            percentiles[level] = final_profits[idx]

        worst_case = percentiles.get(0.05, final_profits[0])
        best_case = percentiles.get(0.95, final_profits[-1])

        # Drawdown percentiles
        dd_percentiles: dict[float, float] = {}
        for level in confidence_levels:
            idx = int(level * n)
            idx = max(0, min(n - 1, idx))
            dd_percentiles[level] = max_drawdowns[idx]

        dd_median = max_drawdowns[n // 2]
        dd_worst = dd_percentiles.get(0.95, max_drawdowns[-1])

        return {
            "success": True,
            "iterations": iterations,
            "ruin_probability": round(ruin_probability, 2),
            "confidence": round(confidence, 2),
            "expected_profit": round(expected_profit, 2),
            "median_profit": round(median_profit, 2),
            "worst_case": round(worst_case, 2),
            "best_case": round(best_case, 2),
            "max_drawdown_median": round(dd_median, 2),
            "max_drawdown_worst": round(dd_worst, 2),
            "percentiles": {
                k: round(v, 2) for k, v in percentiles.items()
            },
            "drawdown_percentiles": {
                k: round(v, 2) for k, v in dd_percentiles.items()
            },
        }
