"""
Stage 9: Backtest Top Passes

Run full backtests on selected passes from Step 8B, apply gates,
calculate composite scores, and select best pass for Monte Carlo.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


# Fields to filter out when extracting input parameters from optimization results
RESULT_FIELDS = {"Pass", "Forward Result", "Back Result", "Custom", "Result"}


class BacktestPassesStage:
    """Stage 9: Run detailed backtests on selected optimization passes."""

    @property
    def name(self) -> str:
        return "9_backtest_passes"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Execute backtests on selected passes.

        Requires:
            - Step 8 (parse_results) completed with passes
            - Step 8B (select_passes) completed with selected_passes
            - MT5 interface for backtest execution

        Args:
            state: Current workflow state
            mt5: MT5 interface (required)

        Returns:
            StageResult with best pass and all results
        """
        from ea_stress.core.metrics import GateResult

        # MT5 interface required
        if mt5 is None:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("MT5 interface required for backtest",),
            )

        # Get compiled EA path from Step 2
        step_2 = state.steps.get("2_compile")
        if not step_2 or not step_2.passed or not step_2.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 2 (compile) must complete successfully first",),
            )
        exe_path = step_2.result.get("exe_path")
        if not exe_path:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No compiled EA path from Step 2",),
            )

        # Get passes from Step 8
        step_8 = state.steps.get("8_parse_results")
        if not step_8 or not step_8.passed or not step_8.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 8 (parse_results) must complete successfully first",),
            )
        all_passes = step_8.result.get("passes", [])
        if not all_passes:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No passes from Step 8",),
            )

        # Get selected passes from Step 8B
        step_8b = state.steps.get("8b_select_passes")
        if not step_8b or not step_8b.passed or not step_8b.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 8B (select_passes) must complete successfully first",),
            )
        selected_pass_nums = step_8b.result.get("selected_passes", [])
        if not selected_pass_nums:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No selected passes from Step 8B",),
            )

        # Build pass lookup
        pass_lookup: dict[int, dict[str, Any]] = {}
        for p in all_passes:
            params = p.get("params", {})
            pass_num = params.get("Pass")
            if pass_num is not None:
                pass_lookup[pass_num] = p

        # Import settings
        import settings

        # Get fixed params for safety overrides
        fixed_params = self._get_fixed_params(settings)

        # Gate thresholds
        min_pf = getattr(settings, "MIN_PROFIT_FACTOR", 1.5)
        max_dd = getattr(settings, "MAX_DRAWDOWN_PCT", 30.0)
        min_trades = getattr(settings, "MIN_TRADES", 50)
        selection_metric = getattr(settings, "BEST_PASS_SELECTION", "score")

        # Run backtests
        results: list[dict[str, Any]] = []
        successful_count = 0
        best_result: dict[str, Any] | None = None
        best_candidate: tuple[float, float] = (-float("inf"), -float("inf"))

        for pass_num in selected_pass_nums:
            pass_data = pass_lookup.get(pass_num)
            if not pass_data:
                continue

            # Extract input params (filter out result fields)
            params = pass_data.get("params", {})
            input_params = {
                k: v for k, v in params.items() if k not in RESULT_FIELDS
            }

            # Add fixed safety params
            input_params.update(fixed_params)

            # Generate deterministic report name
            report_name = (
                f"S9_bt_pass{pass_num}_{state.symbol}_{state.timeframe}_"
                f"{state.workflow_id[:8]}"
            )

            # Run backtest
            try:
                bt_result = mt5.backtest(
                    ea_path=Path(exe_path),
                    symbol=state.symbol,
                    timeframe=state.timeframe,
                    params=input_params,
                    report_name=report_name,
                )
            except Exception as e:
                results.append({
                    "pass_num": pass_num,
                    "success": False,
                    "error": str(e),
                })
                continue

            # Extract metrics
            result_dict: dict[str, Any] = {
                "pass_num": pass_num,
                "success": True,
                "input_params": input_params,
                "profit": bt_result.profit,
                "profit_factor": bt_result.profit_factor,
                "max_drawdown_pct": bt_result.max_drawdown_pct,
                "total_trades": bt_result.total_trades,
                "win_rate": bt_result.win_rate,
                "report_path": bt_result.report_path,
                "forward_result": params.get("Forward Result", 0),
                "back_result": params.get("Back Result", 0),
            }

            # Check gates
            gates_passed = self._check_gates(
                result_dict, min_pf, max_dd, min_trades
            )
            result_dict["gates_passed"] = gates_passed

            if gates_passed:
                successful_count += 1

            # Calculate composite score
            score = self._calculate_composite_score(result_dict, settings)

            # Bonus for positive forward AND back
            forward_result = result_dict.get("forward_result", 0)
            back_result = result_dict.get("back_result", 0)
            is_consistent = forward_result > 0 and back_result > 0
            if is_consistent:
                score = min(10.0, score + 0.5)

            result_dict["composite_score"] = score
            result_dict["is_consistent"] = is_consistent

            results.append(result_dict)

            # Track best pass
            profit = result_dict.get("profit", 0)
            if selection_metric == "profit":
                candidate = (profit, score)
            else:  # 'score' (default)
                candidate = (score, profit)

            if candidate > best_candidate:
                best_candidate = candidate
                best_result = result_dict

        # Overall gate: at least one successful pass
        gate = GateResult(
            name="successful_passes",
            passed=successful_count >= 1,
            value=successful_count,
            threshold=1,
            operator=">=",
        )

        data = {
            "best_result": best_result,
            "all_results": results,
            "successful_count": successful_count,
            "total_count": len(results),
            "selection_metric": selection_metric,
        }

        if gate.passed and best_result:
            return StageResult(
                success=True,
                data=data,
                gate=gate,
                errors=(),
            )
        else:
            return StageResult(
                success=False,
                data=data,
                gate=gate,
                errors=(f"No passes passed all gates ({successful_count}/{len(results)})",),
            )

    def _get_fixed_params(self, settings: Any) -> dict[str, Any]:
        """Get fixed safety param overrides for backtesting."""
        return {
            "EAStressSafety_MaxSpreadPips": getattr(
                settings, "SAFETY_BACKTEST_MAX_SPREAD_PIPS", 10.0
            ),
            "EAStressSafety_MaxSlippagePips": getattr(
                settings, "SAFETY_BACKTEST_MAX_SLIPPAGE_PIPS", 10.0
            ),
        }

    def _check_gates(
        self,
        result: dict[str, Any],
        min_pf: float,
        max_dd: float,
        min_trades: int,
    ) -> bool:
        """Check if result passes all gates."""
        pf = result.get("profit_factor", 0)
        dd = result.get("max_drawdown_pct", 100)
        trades = result.get("total_trades", 0)

        return (
            pf >= min_pf
            and dd <= max_dd
            and trades >= min_trades
        )

    def _calculate_composite_score(
        self, result: dict[str, Any], settings: Any
    ) -> float:
        """Calculate Go Live Score for a backtest result.

        Score formula normalizes key metrics and weights them:
        - consistency (back+forward both positive)
        - total_profit
        - trade_count
        - profit_factor
        - max_drawdown (inverted)

        Returns score in 0-10 range.
        """
        weights = getattr(settings, "GO_LIVE_SCORE_WEIGHTS", {
            "consistency": 0.25,
            "total_profit": 0.25,
            "trade_count": 0.20,
            "profit_factor": 0.15,
            "max_drawdown": 0.15,
        })
        ranges = getattr(settings, "GO_LIVE_SCORE_RANGES", {
            "total_profit": (0, 5000),
            "trade_count": (50, 200),
            "profit_factor": (1.0, 3.0),
            "max_drawdown": (0, 30),
            "consistency_min": (0, 2000),
        })

        # Consistency score
        back_result = result.get("back_result", 0)
        forward_result = result.get("forward_result", 0)
        consistency_min = ranges.get("consistency_min", (0, 2000))

        if back_result > consistency_min[0] and forward_result > consistency_min[0]:
            consistency_score = 1.0
        elif back_result > 0 and forward_result > 0:
            consistency_score = 0.7
        elif back_result > 0 or forward_result > 0:
            consistency_score = 0.3
        else:
            consistency_score = 0.0

        # Profit score
        profit = result.get("profit", 0)
        profit_range = ranges.get("total_profit", (0, 5000))
        profit_score = self._normalize(profit, profit_range[0], profit_range[1])

        # Trade count score
        trades = result.get("total_trades", 0)
        trade_range = ranges.get("trade_count", (50, 200))
        trade_score = self._normalize(trades, trade_range[0], trade_range[1])

        # Profit factor score
        pf = result.get("profit_factor", 0)
        pf_range = ranges.get("profit_factor", (1.0, 3.0))
        pf_score = self._normalize(pf, pf_range[0], pf_range[1])

        # Drawdown score (inverted - lower is better)
        dd = result.get("max_drawdown_pct", 0)
        dd_range = ranges.get("max_drawdown", (0, 30))
        dd_score = 1.0 - self._normalize(dd, dd_range[0], dd_range[1])

        # Weighted sum (0-1) then scale to 0-10
        raw_score = (
            weights.get("consistency", 0.25) * consistency_score
            + weights.get("total_profit", 0.25) * profit_score
            + weights.get("trade_count", 0.20) * trade_score
            + weights.get("profit_factor", 0.15) * pf_score
            + weights.get("max_drawdown", 0.15) * dd_score
        )

        return round(raw_score * 10, 2)

    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize value to 0-1 range, clipped."""
        if max_val <= min_val:
            return 0.0
        normalized = (value - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))
