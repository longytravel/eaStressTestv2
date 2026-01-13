"""
Stage 8B: Select Top Passes

Select top N passes for backtesting using Go Live Score calculation.
"""

from typing import TYPE_CHECKING, Any

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class SelectPassesStage:
    """Stage 8B: Select top passes for detailed backtesting."""

    @property
    def name(self) -> str:
        return "8b_select_passes"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Select top passes using Go Live Score.

        Requires:
            - Step 8 (parse_results) completed with passes

        Two modes:
            - auto_stats_analysis=True: Deterministic scoring (this stage)
            - auto_stats_analysis=False: Workflow pauses for LLM selection

        Args:
            state: Current workflow state
            mt5: Not required for this stage

        Returns:
            StageResult with selected passes
        """
        import settings

        # Get passes from Step 8
        step_8 = state.steps.get("8_parse_results")
        if not step_8 or not step_8.passed or not step_8.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 8 (parse_results) must complete successfully first",),
            )

        passes = step_8.result.get("passes", [])
        if not passes:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No passes from Step 8",),
            )

        # Check if auto mode
        auto_mode = getattr(settings, "AUTO_STATS_ANALYSIS", True)

        if not auto_mode:
            # Pause for LLM selection
            return StageResult(
                success=True,
                data={
                    "paused_for_selection": True,
                    "available_passes": len(passes),
                    "selection_method": "manual",
                },
                gate=None,
                errors=(),
            )

        # Auto mode: Calculate Go Live Score for each pass
        top_n = getattr(settings, "TOP_PASSES_BACKTEST", 30)
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

        # Score all passes
        scores: dict[int, float] = {}
        for p in passes:
            params = p.get("params", {})
            pass_num = params.get("Pass", 0)
            score = self._calculate_go_live_score(p, weights, ranges)
            scores[pass_num] = score

        # Sort passes by score
        scored_passes = sorted(
            passes,
            key=lambda p: scores.get(p.get("params", {}).get("Pass", 0), 0),
            reverse=True,
        )

        # Select top N
        selected = scored_passes[:top_n]
        selected_pass_nums = [
            p.get("params", {}).get("Pass")
            for p in selected
            if p.get("params", {}).get("Pass") is not None
        ]

        # Best pass
        top_pass = selected[0] if selected else None
        top_pass_num = (
            top_pass.get("params", {}).get("Pass")
            if top_pass else None
        )

        data = {
            "selected_passes": selected_pass_nums,
            "selection_method": "auto",
            "top_pass": top_pass_num,
            "scores": scores,
            "total_scored": len(passes),
            "selected_count": len(selected),
        }

        return StageResult(
            success=True,
            data=data,
            gate=None,
            errors=(),
        )

    def _calculate_go_live_score(
        self,
        pass_data: dict[str, Any],
        weights: dict[str, float],
        ranges: dict[str, tuple[float, float]],
    ) -> float:
        """Calculate composite Go Live Score for a pass.

        Score components:
        - consistency: Both back and forward positive (bonus)
        - total_profit: Normalized profit
        - trade_count: Normalized trade count (statistical confidence)
        - profit_factor: Normalized edge quality
        - max_drawdown: Inverted, normalized risk

        Args:
            pass_data: Pass dictionary with metrics
            weights: Weight for each component
            ranges: Normalization ranges for each metric

        Returns:
            Composite score (0-1 range)
        """
        params = pass_data.get("params", {})

        # Consistency: Both back and forward positive
        back_result = params.get("Back Result", pass_data.get("profit", 0))
        forward_result = params.get("Forward Result", 0)

        # Binary consistency bonus
        consistency_min = ranges.get("consistency_min", (0, 2000))
        if back_result > consistency_min[0] and forward_result > consistency_min[0]:
            consistency_score = 1.0
        elif back_result > 0 and forward_result > 0:
            consistency_score = 0.7
        elif back_result > 0 or forward_result > 0:
            consistency_score = 0.3
        else:
            consistency_score = 0.0

        # Profit: Normalize to range
        profit = pass_data.get("profit", 0)
        profit_range = ranges.get("total_profit", (0, 5000))
        profit_score = self._normalize(profit, profit_range[0], profit_range[1])

        # Trade count: Normalize to range
        trades = pass_data.get("total_trades", 0)
        trade_range = ranges.get("trade_count", (50, 200))
        trade_score = self._normalize(trades, trade_range[0], trade_range[1])

        # Profit factor: Normalize to range
        pf = pass_data.get("profit_factor", 0)
        pf_range = ranges.get("profit_factor", (1.0, 3.0))
        pf_score = self._normalize(pf, pf_range[0], pf_range[1])

        # Max drawdown: Inverted (lower is better)
        dd = pass_data.get("max_drawdown_pct", 0)
        dd_range = ranges.get("max_drawdown", (0, 30))
        dd_score = 1.0 - self._normalize(dd, dd_range[0], dd_range[1])

        # Weighted sum
        score = (
            weights.get("consistency", 0.25) * consistency_score
            + weights.get("total_profit", 0.25) * profit_score
            + weights.get("trade_count", 0.20) * trade_score
            + weights.get("profit_factor", 0.15) * pf_score
            + weights.get("max_drawdown", 0.15) * dd_score
        )

        return score

    def _normalize(self, value: float, min_val: float, max_val: float) -> float:
        """Normalize value to 0-1 range.

        Args:
            value: Raw value
            min_val: Minimum of range
            max_val: Maximum of range

        Returns:
            Normalized value clipped to 0-1
        """
        if max_val <= min_val:
            return 0.0
        normalized = (value - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))
