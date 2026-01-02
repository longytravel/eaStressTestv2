"""
Workflow State Manager

Manages persistent state for EA stress test workflows.
State is saved as JSON after each step for recovery and auditing.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import settings


class StateManager:
    """
    Manages workflow state with persistence.

    State structure:
    {
        "workflow_id": "MyEA_20260101_120000",
        "ea_name": "MyEA",
        "ea_path": "/path/to/MyEA.mq5",
        "terminal": "IC_Markets",
        "symbol": "EURUSD",
        "timeframe": "H1",
        "created_at": "2026-01-01T12:00:00",
        "updated_at": "2026-01-01T12:05:00",
        "status": "in_progress",  # pending, in_progress, completed, failed
        "current_step": 5,
        "steps": {
            "1_load_ea": {"status": "passed", "result": {...}, "timestamp": "..."},
            "1b_inject_ontester": {"status": "passed", ...},
            ...
        },
        "metrics": {
            "profit_factor": 2.1,
            "max_drawdown_pct": 18.5,
            ...
        },
        "gates": {
            "profit_factor": {"passed": true, "value": 2.1, "threshold": 1.5},
            ...
        },
        "errors": [],
    }
    """

    STEPS = [
        '1_load_ea',
        '1b_inject_ontester',
        '1c_inject_safety',
        '2_compile',
        '3_extract_params',
        '4_analyze_params',
        '5_validate_trades',
        '6_create_ini',
        '7_run_optimization',
        '8_parse_results',
        '8b_stats_analysis',  # Claude /stats-analyzer selects top 20
        '9_backtest_robust',
        '10_monte_carlo',
        '11_generate_reports',
    ]

    def __init__(
        self,
        ea_name: str,
        ea_path: str,
        terminal: str,
        symbol: str = 'EURUSD',
        timeframe: str = 'H1',
        workflow_id: Optional[str] = None,
        runs_dir: Optional[str] = None,
    ):
        self.runs_dir = Path(runs_dir or settings.RUNS_DIR)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

        # Generate workflow ID if not provided
        if workflow_id is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            workflow_id = f"{ea_name}_{timestamp}"

        self.workflow_id = workflow_id
        self.state_file = self.runs_dir / f"workflow_{workflow_id}.json"

        # Initialize state
        self.state = {
            'workflow_id': workflow_id,
            'ea_name': ea_name,
            'ea_path': str(ea_path),
            'terminal': terminal,
            'symbol': symbol,
            'timeframe': timeframe,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'status': 'pending',
            'current_step': 0,
            'steps': {},
            'metrics': {},
            'gates': {},
            'errors': [],
            'backtest_dates': settings.get_backtest_dates(),
        }

        self._save()

    @classmethod
    def load(cls, workflow_id: str, runs_dir: Optional[str] = None) -> 'StateManager':
        """Load an existing workflow state."""
        runs_dir = Path(runs_dir or settings.RUNS_DIR)
        state_file = runs_dir / f"workflow_{workflow_id}.json"

        if not state_file.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_id}")

        with open(state_file, 'r') as f:
            state = json.load(f)

        # Create instance without initializing new state
        instance = cls.__new__(cls)
        instance.runs_dir = runs_dir
        instance.workflow_id = workflow_id
        instance.state_file = state_file
        instance.state = state

        return instance

    @classmethod
    def list_workflows(cls, runs_dir: Optional[str] = None) -> list[dict]:
        """List all workflow states."""
        runs_dir = Path(runs_dir or settings.RUNS_DIR)

        workflows = []
        for f in sorted(runs_dir.glob('workflow_*.json'), reverse=True):
            try:
                with open(f, 'r') as fp:
                    state = json.load(fp)
                    workflows.append({
                        'workflow_id': state['workflow_id'],
                        'ea_name': state['ea_name'],
                        'status': state['status'],
                        'created_at': state['created_at'],
                        'current_step': state['current_step'],
                        'file': str(f),
                    })
            except:
                pass

        return workflows

    def _save(self) -> None:
        """Save state to JSON file."""
        self.state['updated_at'] = datetime.now().isoformat()
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2, default=str)

    def get_step_index(self, step_name: str) -> int:
        """Get the index of a step by name."""
        try:
            return self.STEPS.index(step_name)
        except ValueError:
            return -1

    def start_step(self, step_name: str) -> None:
        """Mark a step as started."""
        self.state['status'] = 'in_progress'
        self.state['current_step'] = self.get_step_index(step_name)
        self.state['steps'][step_name] = {
            'status': 'in_progress',
            'started_at': datetime.now().isoformat(),
            'result': None,
        }
        self._save()

    def complete_step(
        self,
        step_name: str,
        passed: bool,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Mark a step as completed."""
        step_data = self.state['steps'].get(step_name, {})
        step_data['status'] = 'passed' if passed else 'failed'
        step_data['completed_at'] = datetime.now().isoformat()
        step_data['result'] = result

        if error:
            step_data['error'] = error
            self.state['errors'].append({
                'step': step_name,
                'error': error,
                'timestamp': datetime.now().isoformat(),
            })

        self.state['steps'][step_name] = step_data

        # Update overall status if step failed
        if not passed:
            self.state['status'] = 'failed'

        self._save()

    def update_metrics(self, metrics: dict) -> None:
        """Update the metrics dictionary."""
        self.state['metrics'].update(metrics)
        self._save()

    def update_gates(self, gates: dict) -> None:
        """Update the gates dictionary."""
        self.state['gates'].update(gates)
        self._save()

    def set_status(self, status: str) -> None:
        """Set overall workflow status."""
        self.state['status'] = status
        self._save()

    def complete_workflow(self, passed: bool) -> None:
        """Mark workflow as complete."""
        self.state['status'] = 'completed' if passed else 'failed'
        self.state['completed_at'] = datetime.now().isoformat()
        self._save()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from state."""
        return self.state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in state."""
        self.state[key] = value
        self._save()

    def get_step_result(self, step_name: str) -> Optional[dict]:
        """Get the result of a specific step."""
        step = self.state['steps'].get(step_name, {})
        return step.get('result')

    def is_step_complete(self, step_name: str) -> bool:
        """Check if a step is complete (passed or failed)."""
        step = self.state['steps'].get(step_name, {})
        return step.get('status') in ['passed', 'failed']

    def is_step_passed(self, step_name: str) -> bool:
        """Check if a step passed."""
        step = self.state['steps'].get(step_name, {})
        return step.get('status') == 'passed'

    def all_gates_passed(self) -> bool:
        """Check if all gates have passed."""
        for gate_name, gate_data in self.state['gates'].items():
            if not gate_data.get('passed', False):
                return False
        return True

    def get_summary(self) -> dict:
        """Get a summary of the workflow state."""
        steps_passed = sum(
            1 for s in self.state['steps'].values()
            if s.get('status') == 'passed'
        )
        steps_failed = sum(
            1 for s in self.state['steps'].values()
            if s.get('status') == 'failed'
        )

        return {
            'workflow_id': self.workflow_id,
            'ea_name': self.state['ea_name'],
            'status': self.state['status'],
            'current_step': self.state['current_step'],
            'total_steps': len(self.STEPS),
            'steps_passed': steps_passed,
            'steps_failed': steps_failed,
            'all_gates_passed': self.all_gates_passed(),
            'metrics': self.state['metrics'],
            'errors': self.state['errors'],
        }

    def to_dict(self) -> dict:
        """Return full state as dictionary."""
        return self.state.copy()
