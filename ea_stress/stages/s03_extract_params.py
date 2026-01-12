"""
Stage 3: Extract Parameters

Extract input parameters from EA source code.
"""

from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.metrics import GateResult
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class ExtractParamsStage:
    """Stage 3: Extract input parameters from EA source code."""

    @property
    def name(self) -> str:
        """Step name as used in WORKFLOW_STEPS."""
        return "3_extract_params"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """
        Execute the stage.

        Extracts input parameters from the EA source file. Prefers the
        modified EA (from Stage 1B/1C) if available, otherwise uses original.

        Args:
            state: Current workflow state (provides ea_path and prior step results).
            mt5: MT5 interface (not used for this stage).

        Returns:
            StageResult with params list and params_found gate.
        """
        from ea_stress.core.metrics import GateResult

        # Get source path - prefer modified EA if available
        source_path = state.ea_path

        # Check for modified path from injection stages
        step_1b = state.steps.get("1b_inject_ontester")
        if step_1b and step_1b.passed and step_1b.result:
            modified_path = step_1b.result.get("modified_path")
            if modified_path:
                source_path = modified_path

        try:
            # Use existing extractor from modules/params.py
            from modules.params import extract_params
            params_dicts = extract_params(str(source_path))

            count = len(params_dicts)
            optimizable = sum(1 for p in params_dicts if p.get("optimizable", False))

            # Gate: at least one parameter found
            gate = GateResult(
                name="params_found",
                passed=count > 0,
                value=count,
                threshold=1,
                operator=">=",
            )

            return StageResult(
                success=count > 0,
                data={
                    "params": params_dicts,
                    "count": count,
                    "optimizable": optimizable,
                    "source_path": str(source_path),
                },
                gate=gate,
                errors=() if count > 0 else ("No parameters found in EA",),
            )

        except Exception as e:
            return StageResult(
                success=False,
                data={"source_path": str(source_path)},
                gate=None,
                errors=(str(e),),
            )
