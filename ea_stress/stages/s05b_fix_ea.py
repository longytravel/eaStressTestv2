"""
Stage 5B: Fix EA

Workflow pause point when validation fails.
Tracks fix attempts and signals workflow to pause for /mql5-fixer skill.
"""

from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class FixEAStage:
    """Stage 5B: Workflow pause point when Step 5 validation fails.

    This stage does NOT perform automated fixes. Instead it:
    1. Checks if fix_attempts < max_fix_attempts
    2. Sets workflow status to 'awaiting_ea_fix' if retries remain
    3. Returns data for /mql5-fixer skill to use

    The actual fixing is done externally by /mql5-fixer skill.
    After fix applied, workflow restarts from Step 1.
    """

    @property
    def name(self) -> str:
        return "5b_fix_ea"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Execute fix EA pause point.

        Requires:
            - Step 5 (validate_trades) failed
            - Tracks fix attempts and signals pause

        Args:
            state: Current workflow state
            mt5: MT5 interface (not required for this stage)

        Returns:
            StageResult with fix attempt tracking data
        """
        from ea_stress.core.metrics import GateResult

        # Import settings for max attempts
        import settings

        max_fix_attempts = getattr(settings, "MAX_FIX_ATTEMPTS", 3)

        # Get current fix attempts from state (default 0)
        current_attempts = state.data.get("fix_attempts", 0)

        # Get Step 5 result for context
        step_5 = state.steps.get("5_validate_trades")
        validation_trades = 0
        if step_5 and step_5.result:
            validation_trades = step_5.result.get("total_trades", 0)

        # Get MIN_TRADES threshold for gate
        min_trades = getattr(settings, "MIN_TRADES", 50)

        # Create gate result (same as Step 5)
        gate = GateResult(
            name="minimum_trades",
            passed=validation_trades >= min_trades,
            value=validation_trades,
            threshold=min_trades,
            operator=">=",
        )

        # Check if we have retries remaining
        if current_attempts < max_fix_attempts:
            # Increment attempt counter
            new_attempts = current_attempts + 1

            # Prepare data for /mql5-fixer skill
            data = {
                "fix_attempts": new_attempts,
                "max_fix_attempts": max_fix_attempts,
                "awaiting_fix": True,
                "validation_trades": validation_trades,
                "ea_path": str(state.ea_path) if state.ea_path else None,
            }

            # This is a workflow pause point - returns success=False
            # because the EA still doesn't pass validation.
            # The 'awaiting_fix' flag signals workflow to pause.
            return StageResult(
                success=False,
                data=data,
                gate=gate,
                errors=(
                    f"Attempt {new_attempts}/{max_fix_attempts}: "
                    f"EA needs fix ({validation_trades} trades < {min_trades} minimum). "
                    f"Workflow paused for /mql5-fixer.",
                ),
            )
        else:
            # Max attempts exhausted
            data = {
                "fix_attempts": current_attempts,
                "max_fix_attempts": max_fix_attempts,
                "awaiting_fix": False,
                "validation_trades": validation_trades,
            }

            return StageResult(
                success=False,
                data=data,
                gate=gate,
                errors=(
                    f"Max fix attempts ({max_fix_attempts}) exhausted. "
                    f"EA still only produces {validation_trades} trades.",
                ),
            )
