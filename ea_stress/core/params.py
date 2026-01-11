"""
Parameter Domain Models

Dataclasses for EA input parameters and optimization ranges.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, Any


# Valid MQL5 base types (normalized forms)
MQL5_BASE_TYPES: frozenset[str] = frozenset({
    "int",
    "double",
    "bool",
    "string",
    "enum",
    "datetime",
    "color",
})


def is_valid_base_type(base_type: str) -> bool:
    """Check if a base type is valid.

    Args:
        base_type: The normalized type string to check.

    Returns:
        True if the type is in MQL5_BASE_TYPES.
    """
    return base_type in MQL5_BASE_TYPES


@dataclass(frozen=True)
class Parameter:
    """
    Represents an extracted EA input parameter.

    Extracted from EA source code in Step 3.

    Attributes:
        name: Parameter name (identifier).
        type: MQL5 type as written (e.g., "double", "ENUM_TIMEFRAMES").
        base_type: Normalized type (int, double, bool, string, enum, datetime, color).
        default: Default value as string, or None if not specified.
        comment: Inline comment after semicolon, or None.
        line: Line number in source (1-indexed).
        optimizable: True for input + numeric types (int, double).
    """
    name: str
    type: str
    base_type: str
    default: Optional[str] = None
    comment: Optional[str] = None
    line: int = 0
    optimizable: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "type": self.type,
            "base_type": self.base_type,
            "default": self.default,
            "comment": self.comment,
            "line": self.line,
            "optimizable": self.optimizable,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Parameter":
        """Create Parameter from dictionary."""
        return cls(
            name=data["name"],
            type=data["type"],
            base_type=data["base_type"],
            default=data.get("default"),
            comment=data.get("comment"),
            line=data.get("line", 0),
            optimizable=data.get("optimizable", False),
        )


@dataclass
class OptimizationRange:
    """
    Represents an optimization range for a parameter.

    Produced by LLM in Step 4 (param analysis).

    Attributes:
        name: Parameter name.
        start: Range start value.
        stop: Range end value.
        step: Step size (None for bool).
        optimize: True to include in optimization.
        fixed_value: If optimize=False, use this value.
        skip_reason: Why parameter is skipped from optimization.
        category: Parameter category (risk, strategy, filter, etc.).
        rationale: Explanation of range choice.
    """
    name: str
    start: Union[int, float, bool]
    stop: Union[int, float, bool]
    step: Optional[Union[int, float]] = None
    optimize: bool = True
    fixed_value: Optional[Any] = None
    skip_reason: Optional[str] = None
    category: Optional[str] = None
    rationale: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate range values after initialization."""
        errors = self._validate()
        if errors:
            raise ValueError(f"Invalid OptimizationRange: {'; '.join(errors)}")

    def _validate(self) -> list[str]:
        """Internal validation, returns list of error messages."""
        errors = []

        # Skip validation for booleans
        if isinstance(self.start, bool) and isinstance(self.stop, bool):
            return errors

        # For numeric types, validate start <= stop
        if isinstance(self.start, (int, float)) and isinstance(self.stop, (int, float)):
            if self.start > self.stop:
                errors.append(f"start ({self.start}) must be <= stop ({self.stop})")

            # If optimizing, step must be > 0
            if self.optimize and self.step is not None:
                if self.step <= 0:
                    errors.append(f"step ({self.step}) must be > 0 when optimizing")

        return errors

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "start": self.start,
            "stop": self.stop,
            "step": self.step,
            "optimize": self.optimize,
            "fixed_value": self.fixed_value,
            "skip_reason": self.skip_reason,
            "category": self.category,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OptimizationRange":
        """Create OptimizationRange from dictionary."""
        return cls(
            name=data["name"],
            start=data["start"],
            stop=data["stop"],
            step=data.get("step"),
            optimize=data.get("optimize", True),
            fixed_value=data.get("fixed_value"),
            skip_reason=data.get("skip_reason"),
            category=data.get("category"),
            rationale=data.get("rationale"),
        )


def validate_range(r: OptimizationRange) -> list[str]:
    """
    Validate an OptimizationRange.

    Args:
        r: The OptimizationRange to validate.

    Returns:
        List of error messages. Empty list means valid.
    """
    errors = []

    # Check name is non-empty
    if not r.name or not r.name.strip():
        errors.append("name must be non-empty")

    # Skip validation for booleans
    if isinstance(r.start, bool) and isinstance(r.stop, bool):
        return errors

    # For numeric types
    if isinstance(r.start, (int, float)) and isinstance(r.stop, (int, float)):
        # Validate start <= stop
        if r.start > r.stop:
            errors.append(f"start ({r.start}) must be <= stop ({r.stop})")

        # If optimizing, step must be > 0
        if r.optimize:
            if r.step is None:
                errors.append("step is required when optimizing numeric parameters")
            elif r.step <= 0:
                errors.append(f"step ({r.step}) must be > 0 when optimizing")

    # If not optimizing, should have fixed_value or sensible start==stop
    if not r.optimize:
        if r.fixed_value is None and r.start != r.stop:
            errors.append("fixed_value should be set when optimize=False and start != stop")

    return errors
