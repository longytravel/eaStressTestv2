"""
Stage 1: Load EA

Verify EA file exists and is accessible.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.metrics import GateResult
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class LoadEAStage:
    """Stage 1: Verify EA file exists."""

    @property
    def name(self) -> str:
        """Step name as used in WORKFLOW_STEPS."""
        return "1_load_ea"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """
        Execute the stage.

        Verifies that the EA file at state.ea_path exists.

        Args:
            state: Current workflow state (provides ea_path).
            mt5: MT5 interface (not used for this stage).

        Returns:
            StageResult with file_exists gate.
        """
        from ea_stress.core.metrics import GateResult

        ea_path = Path(state.ea_path)
        exists = ea_path.exists()

        gate = GateResult(
            name="file_exists",
            passed=exists,
            value=1 if exists else 0,
            threshold=1,
            operator="==",
        )

        return StageResult(
            success=exists,
            data={"path": str(ea_path), "exists": exists},
            gate=gate,
            errors=() if exists else (f"EA file not found: {ea_path}",),
        )
