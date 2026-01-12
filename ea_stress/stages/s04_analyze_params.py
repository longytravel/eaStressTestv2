"""
Stage 4: Analyze Parameters (LLM Pause Point)

This stage is special - it's a pause point where the workflow
waits for external input (from /param-analyzer skill or auto-analysis).
"""

from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.metrics import GateResult
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class AnalyzeParamsStage:
    """Stage 4: Analyze parameters (LLM pause point).

    This stage is special - it's a pause point where the workflow
    waits for external input (from /param-analyzer skill or auto-analysis).

    When executed WITHOUT analysis data: Returns success=True with empty data,
    and the pipeline should transition to AWAITING_PARAM_ANALYSIS status.

    When executed WITH analysis data (via continue_with_params): Validates
    and stores the wide_validation_params and optimization_ranges.
    """

    def __init__(self) -> None:
        """Initialize the stage with no analysis data."""
        self._wide_params: dict | None = None
        self._opt_ranges: list[dict] | None = None

    @property
    def name(self) -> str:
        """Step name as used in WORKFLOW_STEPS."""
        return "4_analyze_params"

    def set_analysis_data(
        self,
        wide_validation_params: dict,
        optimization_ranges: list[dict],
    ) -> None:
        """Set analysis data before execution (called by pipeline on resume).

        Args:
            wide_validation_params: Parameter values for trade validation (Step 5).
            optimization_ranges: Parameter ranges for optimization (Step 6+).
        """
        self._wide_params = wide_validation_params
        self._opt_ranges = optimization_ranges

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """
        Execute the stage.

        If no analysis data has been set via set_analysis_data(), returns
        a "waiting" status for the pipeline to pause at.

        If analysis data is present, validates it and returns success with
        the params/ranges stored in data.

        Args:
            state: Current workflow state.
            mt5: MT5 interface (not used for this stage).

        Returns:
            StageResult with analysis data or awaiting status.
        """
        from ea_stress.core.metrics import GateResult

        # Check if we have analysis data
        if self._wide_params is None or self._opt_ranges is None:
            # No analysis data - this is the initial pause
            return StageResult(
                success=True,  # Step "succeeds" but pipeline pauses
                data={
                    "status": "awaiting_param_analysis",
                    "message": "Waiting for parameter analysis from /param-analyzer skill",
                },
                gate=None,
                errors=(),
            )

        # Validate the analysis data
        errors = self._validate_analysis()
        if errors:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=tuple(errors),
            )

        # Analysis data valid - store and return success
        gate = GateResult(
            name="params_analyzed",
            passed=True,
            value=len(self._opt_ranges),
            threshold=1,
            operator=">=",
        )

        return StageResult(
            success=True,
            data={
                "source": "param_analysis",
                "wide_validation_params": self._wide_params,
                "wide_param_count": len(self._wide_params),
                "optimization_ranges": self._opt_ranges,
                "optimization_param_count": len(self._opt_ranges),
            },
            gate=gate,
            errors=(),
        )

    def _validate_analysis(self) -> list[str]:
        """Validate the analysis data.

        Returns:
            List of error messages. Empty list means valid.
        """
        errors: list[str] = []

        if not self._wide_params:
            errors.append("wide_validation_params is empty")

        if not self._opt_ranges:
            errors.append("optimization_ranges is empty")

        # Check each range has required fields
        required_fields = {"name", "start", "step", "stop", "optimize"}
        for i, r in enumerate(self._opt_ranges or []):
            missing = required_fields - set(r.keys())
            if missing:
                errors.append(f"Range {i} missing fields: {missing}")

        return errors
