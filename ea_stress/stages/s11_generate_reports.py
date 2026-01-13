"""
Stage 11: Generate Reports

Generate dashboard, leaderboard, and boards reports.
This stage ALWAYS runs, even when earlier steps fail.
"""

from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class GenerateReportsStage:
    """Stage 11: Generate dashboard, leaderboard, and boards reports.

    This stage:
    1. Calculates final composite score from state metrics
    2. Checks go-live readiness (all critical gates passed)
    3. Generates failure diagnosis if not ready
    4. Generates three report types using existing reports module

    This stage ALWAYS runs, even when earlier steps fail.
    Failed workflows still get dashboards showing what went wrong.

    Gate: None (informational step)
    """

    @property
    def name(self) -> str:
        return "11_generate_reports"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Execute report generation.

        Note: MT5 interface is not required for this stage.

        Args:
            state: Current workflow state
            mt5: MT5 interface (not used, kept for protocol compliance)

        Returns:
            StageResult with report paths and go-live status
        """
        # Import report generators and gates
        from engine import gates
        from reports.workflow_dashboard import generate_dashboard_from_workflow
        from reports.leaderboard import generate_leaderboard
        from reports.boards import generate_boards

        # Calculate composite score
        metrics = state.metrics if hasattr(state, 'metrics') else {}
        # Handle both WorkflowState object and dict access
        if hasattr(metrics, 'to_dict'):
            metrics_dict = metrics.to_dict() if hasattr(metrics.to_dict, '__call__') else {}
        elif isinstance(metrics, dict):
            metrics_dict = metrics
        else:
            # Try to get metrics from state.get()
            metrics_dict = state.get('metrics', {}) if hasattr(state, 'get') else {}

        composite_score = gates.calculate_composite_score(metrics_dict)

        # Check go-live readiness
        state_dict = state.to_dict() if hasattr(state, 'to_dict') else {}
        go_live = gates.check_go_live_ready(state_dict)
        go_live_ready = go_live.get('go_live_ready', False)

        # Generate failure diagnosis if not ready
        diagnoses = []
        if not go_live_ready:
            gates_dict = state_dict.get('gates', {})
            diagnoses = gates.diagnose_failure(gates_dict, metrics_dict)

        # Save state before generating reports (if state supports it)
        if hasattr(state, 'save'):
            state.save()

        # Get state file path for dashboard generation
        state_file = None
        if hasattr(state, 'state_file'):
            state_file = str(state.state_file)

        # Generate dashboard
        dashboard_path = None
        if state_file:
            try:
                dashboard_path = generate_dashboard_from_workflow(
                    state_file,
                    run_backtests=False,  # Fast mode - optimization data only
                    open_browser=False,
                )
            except Exception as e:
                # Dashboard generation failure is not fatal
                pass

        # Update leaderboard
        leaderboard_path = None
        try:
            leaderboard_path = generate_leaderboard(open_browser=False)
        except Exception:
            # Leaderboard update failure is not fatal
            pass

        # Update boards
        boards_path = None
        try:
            boards_path = generate_boards(open_browser=False)
        except Exception:
            # Boards update failure is not fatal
            pass

        # Build result data
        data = {
            'dashboard_path': dashboard_path,
            'leaderboard_path': leaderboard_path,
            'boards_path': boards_path,
            'composite_score': composite_score,
            'go_live_ready': go_live_ready,
            'go_live': go_live,
            'diagnoses': diagnoses,
        }

        # This stage always succeeds (informational step)
        return StageResult(
            success=True,
            data=data,
            gate=None,  # No gate for informational step
            errors=(),
        )
