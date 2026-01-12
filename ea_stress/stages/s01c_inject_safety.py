"""
Stage 1C: Inject Safety

Inject safety guards into modified EA.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class InjectSafetyStage:
    """Stage 1C: Inject safety guards into modified EA."""

    @property
    def name(self) -> str:
        """Step name as used in WORKFLOW_STEPS."""
        return "1c_inject_safety"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """
        Execute the stage.

        Reads modified_path from Step 1B result and injects safety guards.

        Args:
            state: Current workflow state (provides steps with 1B result).
            mt5: MT5 interface (not used for this stage).

        Returns:
            StageResult with safety_injected status.
        """
        # Get the modified EA path from Step 1B
        step_1b = state.steps.get("1b_inject_ontester")
        if not step_1b or not step_1b.passed:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 1B must complete successfully first",),
            )

        modified_path = step_1b.result.get("modified_path") if step_1b.result else None
        if not modified_path:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No modified EA path from Step 1B",),
            )

        # Lazy import existing module
        from modules.injector import inject_safety

        try:
            content = Path(modified_path).read_text(encoding="utf-8")
            content, injected = inject_safety(content)
            Path(modified_path).write_text(content, encoding="utf-8")

            return StageResult(
                success=True,
                data={
                    "path": modified_path,
                    "safety_injected": injected,
                },
                gate=None,  # No gate for this step
                errors=(),
            )
        except Exception as e:
            return StageResult(
                success=False,
                data={"path": modified_path},
                gate=None,
                errors=(str(e),),
            )
