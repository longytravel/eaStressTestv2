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
    "ExtractParamsStage",
    "AnalyzeParamsStage",
    "ValidateTradesStage",
    "FixEAStage",
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
    if name == "ExtractParamsStage":
        from ea_stress.stages.s03_extract_params import ExtractParamsStage
        return ExtractParamsStage
    if name == "AnalyzeParamsStage":
        from ea_stress.stages.s04_analyze_params import AnalyzeParamsStage
        return AnalyzeParamsStage
    if name == "ValidateTradesStage":
        from ea_stress.stages.s05_validate_trades import ValidateTradesStage
        return ValidateTradesStage
    if name == "FixEAStage":
        from ea_stress.stages.s05b_fix_ea import FixEAStage
        return FixEAStage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
