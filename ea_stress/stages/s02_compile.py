"""
Stage 2: Compile EA

Compile the EA using MetaEditor64 via MT5Interface.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.metrics import GateResult
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class CompileStage:
    """Stage 2: Compile the EA using MetaEditor64."""

    @property
    def name(self) -> str:
        """Step name as used in WORKFLOW_STEPS."""
        return "2_compile"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """
        Execute the stage.

        Compiles the EA using MT5Interface.compile(). Prefers the modified EA
        from Step 1B if available.

        Args:
            state: Current workflow state (provides ea_path, step results).
            mt5: MT5 interface (required for this stage).

        Returns:
            StageResult with compilation results and gate.
        """
        from ea_stress.core.metrics import GateResult

        if mt5 is None:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("MT5 interface required for compilation",),
            )

        # Get path to compile - prefer modified EA from Step 1B if available
        step_1b = state.steps.get("1b_inject_ontester")
        if step_1b and step_1b.passed and step_1b.result:
            ea_path = Path(step_1b.result.get("modified_path", state.ea_path))
        else:
            ea_path = Path(state.ea_path)

        # Compile using MT5Interface
        result = mt5.compile(ea_path)

        # Create gate result
        error_count = len(result.errors)
        gate = GateResult(
            name="compilation",
            passed=result.success and error_count == 0,
            value=error_count,
            threshold=0,
            operator="==",
        )

        if result.success:
            return StageResult(
                success=True,
                data={
                    "source_path": str(ea_path),
                    "exe_path": result.exe_path,
                    "errors": list(result.errors),
                    "warnings": list(result.warnings),
                },
                gate=gate,
                errors=(),
            )
        else:
            return StageResult(
                success=False,
                data={
                    "source_path": str(ea_path),
                    "errors": list(result.errors),
                    "warnings": list(result.warnings),
                },
                gate=gate,
                errors=result.errors,
            )
