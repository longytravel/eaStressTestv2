"""
Stage Framework Package

Exports Stage protocol and supporting types for workflow stage implementations.
"""

from ea_stress.stages.base import StageResult, Stage, StageContext

__all__ = [
    "StageResult",
    "Stage",
    "StageContext",
    # Stage implementations
    "LoadEAStage",
    "InjectOnTesterStage",
    "InjectSafetyStage",
    "CompileStage",
]


def __getattr__(name: str):
    """Lazy imports for stage implementations."""
    if name == "LoadEAStage":
        from ea_stress.stages.s01_load import LoadEAStage
        return LoadEAStage
    if name == "InjectOnTesterStage":
        from ea_stress.stages.s01b_inject_ontester import InjectOnTesterStage
        return InjectOnTesterStage
    if name == "InjectSafetyStage":
        from ea_stress.stages.s01c_inject_safety import InjectSafetyStage
        return InjectSafetyStage
    if name == "CompileStage":
        from ea_stress.stages.s02_compile import CompileStage
        return CompileStage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
