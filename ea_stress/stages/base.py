"""
Stage Framework Base Module

Defines the Stage protocol, StageResult, and StageContext for implementing workflow stages.
"""

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ea_stress.core.metrics import GateResult


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
