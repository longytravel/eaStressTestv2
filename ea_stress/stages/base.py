"""
Stage Framework Base Module

Defines the Stage protocol, StageResult, and StageContext for implementing workflow stages.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from ea_stress.core.metrics import GateResult
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


@dataclass(frozen=True)
class StageResult:
    """
    Result of executing a stage.

    Frozen dataclass for immutable operation results.

    Attributes:
        success: Whether stage passed.
        data: Stage-specific output data.
        gate: Gate check result (if applicable).
        errors: Error messages.
    """
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    gate: "GateResult | None" = None
    errors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "data": self.data,
            "gate": self.gate.to_dict() if self.gate else None,
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageResult":
        """Create StageResult from dictionary."""
        from ea_stress.core.metrics import GateResult

        gate_data = data.get("gate")
        gate = GateResult.from_dict(gate_data) if gate_data else None

        return cls(
            success=data.get("success", False),
            data=data.get("data", {}),
            gate=gate,
            errors=tuple(data.get("errors", [])),
        )


class Stage(Protocol):
    """Protocol for workflow stages.

    Each stage:
    1. Has a name (step identifier like "1_load_ea")
    2. Takes inputs via constructor or execute params
    3. Returns StageResult with success/data/gate/errors
    """

    @property
    def name(self) -> str:
        """Step name as used in WORKFLOW_STEPS (e.g., '1_load_ea')."""
        ...

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Execute the stage.

        Args:
            state: Current workflow state (for reading prior step results)
            mt5: MT5 interface for operations requiring MT5 (compile, backtest, optimize)
                 Pass None for stages that don't need MT5.

        Returns:
            StageResult with success status, output data, and gate result
        """
        ...
