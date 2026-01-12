"""
Stage 5: Validate Trades

Run validation backtest to prove the EA can generate trades.
Uses wide_validation_params from Step 4 with loose safety limits.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class ValidateTradesStage:
    """Stage 5: Run validation backtest to prove EA generates trades."""

    @property
    def name(self) -> str:
        return "5_validate_trades"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Execute trade validation backtest.

        Requires:
            - Step 2 (compile) completed with exe_path
            - Step 4 (analyze_params) completed with wide_validation_params
            - MT5 interface for backtest execution

        Args:
            state: Current workflow state
            mt5: MT5 interface (required)

        Returns:
            StageResult with trade count gate check
        """
        from ea_stress.core.metrics import GateResult

        # MT5 interface is required for backtest
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

        # Get wide_validation_params from Step 4
        step_4 = state.steps.get("4_analyze_params")
        if not step_4 or not step_4.passed or not step_4.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 4 (analyze params) must complete successfully first",),
            )
        wide_params = step_4.result.get("wide_validation_params")
        if not wide_params:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No wide_validation_params from Step 4",),
            )

        # Import settings for thresholds
        import settings

        # Apply safety param overrides for validation (loose limits)
        params = dict(wide_params)
        params["EAStressSafety_MaxSpreadPips"] = getattr(
            settings, "SAFETY_VALIDATION_MAX_SPREAD_PIPS", 500.0
        )
        params["EAStressSafety_MaxSlippagePips"] = getattr(
            settings, "SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS", 500.0
        )

        # Generate deterministic report name
        report_name = f"S5_validate_{state.symbol}_{state.timeframe}_{state.workflow_id[:8]}"

        # Run backtest
        result = mt5.backtest(
            ea_path=Path(exe_path),
            symbol=state.symbol,
            timeframe=state.timeframe,
            params=params,
            report_name=report_name,
        )

        # Check trade count against threshold
        min_trades = getattr(settings, "MIN_TRADES", 50)
        trades = result.total_trades

        gate = GateResult(
            name="minimum_trades",
            passed=trades >= min_trades,
            value=trades,
            threshold=min_trades,
            operator=">=",
        )

        data = {
            "total_trades": trades,
            "profit": result.profit,
            "profit_factor": result.profit_factor,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate": result.win_rate,
            "report_path": result.report_path,
        }

        if gate.passed:
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
                errors=(f"Only {trades} trades, minimum is {min_trades}",),
            )
