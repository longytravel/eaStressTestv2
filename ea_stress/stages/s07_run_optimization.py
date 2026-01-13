"""
Stage 7: Run Optimization

Runs MT5 genetic optimization using the INI configuration from Step 6.
"""

import time
from pathlib import Path
from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class RunOptimizationStage:
    """Stage 7: Run MT5 genetic optimization."""

    @property
    def name(self) -> str:
        return "7_run_optimization"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Execute MT5 optimization.

        Requires:
            - Step 2 (compile) completed with exe_path
            - Step 4 (analyze_params) completed with optimization_ranges
            - Step 6 (create_ini) completed with report_name
            - MT5 interface for optimization execution

        Args:
            state: Current workflow state
            mt5: MT5 interface (required)

        Returns:
            StageResult with xml_path and pass counts
        """
        import settings
        from ea_stress.core.metrics import GateResult

        # MT5 interface is required for optimization
        if mt5 is None:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("MT5 interface required for optimization",),
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

        # Get optimization_ranges from Step 4
        step_4 = state.steps.get("4_analyze_params")
        if not step_4 or not step_4.passed or not step_4.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 4 (analyze params) must complete successfully first",),
            )
        optimization_ranges = step_4.result.get("optimization_ranges")
        if not optimization_ranges:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No optimization_ranges from Step 4",),
            )

        # Get report_name from Step 6
        step_6 = state.steps.get("6_create_ini")
        if not step_6 or not step_6.passed or not step_6.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 6 (create INI) must complete successfully first",),
            )
        report_name = step_6.result.get("report_name")
        if not report_name:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No report_name from Step 6",),
            )

        # Get timeout from settings
        timeout = getattr(settings, "OPTIMIZATION_TIMEOUT", 36000)  # 10 hours default

        # Record start time for duration tracking
        start_time = time.time()

        # Run optimization
        result = mt5.optimize(
            ea_path=Path(exe_path),
            symbol=state.symbol,
            timeframe=state.timeframe,
            param_ranges=optimization_ranges,
            report_name=report_name,
            timeout=timeout,
        )

        # Calculate duration
        duration_seconds = time.time() - start_time

        # Gate: at least one valid pass
        passes_found = result.passes_count
        gate = GateResult(
            name="passes_found",
            passed=passes_found > 0,
            value=passes_found,
            threshold=1,
            operator=">=",
        )

        data = {
            "xml_path": result.xml_path,
            "report_name": report_name,
            "duration_seconds": duration_seconds,
            "passes_count": passes_found,
            "best_result": result.best_result,
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
                errors=(
                    f"Optimization found {passes_found} passes, minimum is 1",
                    *result.errors,
                ),
            )
