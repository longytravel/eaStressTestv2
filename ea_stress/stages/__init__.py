"""
Stage Framework Package

Exports Stage protocol and supporting types for workflow stage implementations.
"""

from ea_stress.stages.base import StageResult

__all__ = [
    "StageResult",
]


def __getattr__(name: str):
    """Lazy imports for stage implementations (to be added later)."""
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
