"""
Stage 1B: Inject OnTester

Inject OnTester function for custom optimization criterion.
"""

from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class InjectOnTesterStage:
    """Stage 1B: Inject OnTester function for custom optimization criterion."""

    @property
    def name(self) -> str:
        """Step name as used in WORKFLOW_STEPS."""
        return "1b_inject_ontester"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """
        Execute the stage.

        Injects OnTester function into the EA source code using modules/injector.

        Args:
            state: Current workflow state (provides ea_path).
            mt5: MT5 interface (not used for this stage).

        Returns:
            StageResult with modified_path in data.
        """
        # Lazy import existing module
        from modules.injector import create_modified_ea

        ea_path = state.ea_path

        # Call existing injector - OnTester only, not safety guards
        result = create_modified_ea(
            str(ea_path),
            inject_tester=True,
            inject_guards=False,  # Safety guards handled in separate step 1C
        )

        if result["success"]:
            return StageResult(
                success=True,
                data={
                    "original_path": str(ea_path),
                    "modified_path": result["modified_path"],
                    "ontester_injected": result.get("ontester_injected", True),
                    "safety_injected": False,
                },
                gate=None,  # No gate for this step
                errors=(),
            )
        else:
            return StageResult(
                success=False,
                data={"original_path": str(ea_path)},
                gate=None,
                errors=tuple(result.get("errors", ["OnTester injection failed"])),
            )
