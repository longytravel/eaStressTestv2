"""
EA Stress Test - Core Domain Models

This package contains pure domain models:
- params: Parameter and OptimizationRange dataclasses
- metrics: TradeMetrics, GateResult, and scoring functions
- state: WorkflowState and related types
"""

from ea_stress.core.params import (
    Parameter,
    OptimizationRange,
    MQL5_BASE_TYPES,
    validate_range,
    is_valid_base_type,
)
from ea_stress.core.metrics import (
    TradeMetrics,
    GateResult,
    MonteCarloResult,
    GO_LIVE_SCORE_WEIGHTS,
    GO_LIVE_SCORE_RANGES,
    calculate_composite_score,
    normalize_value,
)
from ea_stress.core.state import (
    WorkflowStatus,
    StepResult,
    WorkflowState,
    WORKFLOW_STEPS,
    get_step_result,
    is_step_complete,
    get_next_step,
    to_dict,
    from_dict,
)

__all__ = [
    # params
    "Parameter",
    "OptimizationRange",
    "MQL5_BASE_TYPES",
    "validate_range",
    "is_valid_base_type",
    # metrics
    "TradeMetrics",
    "GateResult",
    "MonteCarloResult",
    "GO_LIVE_SCORE_WEIGHTS",
    "GO_LIVE_SCORE_RANGES",
    "calculate_composite_score",
    "normalize_value",
    # state
    "WorkflowStatus",
    "StepResult",
    "WorkflowState",
    "WORKFLOW_STEPS",
    "get_step_result",
    "is_step_complete",
    "get_next_step",
    "to_dict",
    "from_dict",
]
