"""
Workflow State Domain Models

Dataclasses for workflow state, steps, and status tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class WorkflowStatus(Enum):
    """Workflow status values."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_PARAM_ANALYSIS = "awaiting_param_analysis"
    AWAITING_STATS_ANALYSIS = "awaiting_stats_analysis"
    AWAITING_EA_FIX = "awaiting_ea_fix"
    COMPLETED = "completed"
    FAILED = "failed"


# All workflow steps in order
WORKFLOW_STEPS: tuple[str, ...] = (
    "1_load_ea",
    "1b_inject_ontester",
    "1c_inject_safety",
    "2_compile",
    "3_extract_params",
    "4_analyze_params",
    "5_validate_trades",
    "6_create_ini",
    "7_run_optimization",
    "8_parse_results",
    "8b_stats_analysis",
    "9_backtest_robust",
    "10_monte_carlo",
    "11_generate_reports",
    "12_stress_scenarios",
    "13_forward_windows",
    "14_multi_pair",
)


@dataclass
class StepResult:
    """
    Result of a workflow step.

    Attributes:
        step_name: Step identifier (e.g., "1_load_ea", "3_extract_params").
        passed: True if step succeeded, False if failed.
        result: Step-specific result data.
        timestamp: Completion time in ISO format.
        error: Error message if step failed.
    """
    step_name: str
    passed: bool
    result: Optional[dict] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "step_name": self.step_name,
            "passed": self.passed,
            "result": self.result,
            "timestamp": self.timestamp,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StepResult":
        """Create StepResult from dictionary."""
        return cls(
            step_name=data["step_name"],
            passed=data["passed"],
            result=data.get("result"),
            timestamp=data.get("timestamp"),
            error=data.get("error"),
        )


@dataclass
class WorkflowState:
    """
    Complete workflow state.

    Tracks the state of an EA stress test workflow.

    Attributes:
        workflow_id: Unique workflow identifier.
        ea_name: Name of the EA being tested.
        ea_path: Path to the EA source file.
        terminal: MT5 terminal identifier.
        symbol: Trading symbol (default: EURUSD).
        timeframe: Chart timeframe (default: H1).
        status: Current workflow status.
        current_step: Name of current/last step.
        steps: Map of step name to StepResult.
        metrics: Collected metrics (profit, trades, etc.).
        gates: Gate check results.
        errors: List of error messages.
        created_at: Workflow creation time (ISO format).
        updated_at: Last update time (ISO format).
    """
    workflow_id: str
    ea_name: str
    ea_path: str
    terminal: str
    symbol: str = "EURUSD"
    timeframe: str = "H1"
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step: Optional[str] = None
    steps: dict[str, StepResult] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    gates: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def get_step_result(state: WorkflowState, step_name: str) -> Optional[StepResult]:
    """
    Get the result of a specific step.

    Args:
        state: The workflow state.
        step_name: Name of the step to get.

    Returns:
        StepResult if step exists, None otherwise.
    """
    return state.steps.get(step_name)


def is_step_complete(state: WorkflowState, step_name: str) -> bool:
    """
    Check if a step is complete (passed or failed).

    Args:
        state: The workflow state.
        step_name: Name of the step to check.

    Returns:
        True if step has a result, False otherwise.
    """
    return step_name in state.steps


def get_next_step(state: WorkflowState) -> Optional[str]:
    """
    Get the next step to execute.

    Finds the first step that hasn't been completed yet.

    Args:
        state: The workflow state.

    Returns:
        Name of next step, or None if all steps complete.
    """
    for step in WORKFLOW_STEPS:
        if step not in state.steps:
            return step
    return None


def to_dict(state: WorkflowState) -> dict:
    """
    Convert WorkflowState to dictionary for JSON serialization.

    Args:
        state: The workflow state to convert.

    Returns:
        Dictionary representation.
    """
    return {
        "workflow_id": state.workflow_id,
        "ea_name": state.ea_name,
        "ea_path": state.ea_path,
        "terminal": state.terminal,
        "symbol": state.symbol,
        "timeframe": state.timeframe,
        "status": state.status.value,
        "current_step": state.current_step,
        "steps": {
            name: step.to_dict() for name, step in state.steps.items()
        },
        "metrics": state.metrics,
        "gates": state.gates,
        "errors": state.errors,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def from_dict(data: dict) -> WorkflowState:
    """
    Create WorkflowState from dictionary.

    Args:
        data: Dictionary with workflow state data.

    Returns:
        WorkflowState instance.
    """
    # Parse status enum
    status_str = data.get("status", "pending")
    try:
        status = WorkflowStatus(status_str)
    except ValueError:
        status = WorkflowStatus.PENDING

    # Parse steps
    steps_data = data.get("steps", {})
    steps = {}
    for name, step_dict in steps_data.items():
        # Handle both old format (without step_name) and new format
        if "step_name" not in step_dict:
            step_dict = dict(step_dict)
            step_dict["step_name"] = name
        steps[name] = StepResult.from_dict(step_dict)

    return WorkflowState(
        workflow_id=data["workflow_id"],
        ea_name=data["ea_name"],
        ea_path=data["ea_path"],
        terminal=data["terminal"],
        symbol=data.get("symbol", "EURUSD"),
        timeframe=data.get("timeframe", "H1"),
        status=status,
        current_step=data.get("current_step"),
        steps=steps,
        metrics=data.get("metrics", {}),
        gates=data.get("gates", {}),
        errors=data.get("errors", []),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
    )
