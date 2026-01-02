"""
Tests for State Manager

Tests workflow state persistence and management.
"""
import pytest
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.state import StateManager


class TestStateManagerInit:
    """Tests for StateManager initialization."""

    def test_create_new_state(self, temp_dir):
        """Test creating new state manager."""
        state = StateManager(
            ea_name='TestEA',
            ea_path='/path/to/TestEA.mq5',
            terminal='TestBroker',
            runs_dir=str(temp_dir),
        )

        assert state.workflow_id.startswith('TestEA_')
        assert state.state_file.exists()

    def test_state_file_created(self, temp_dir):
        """Test state file is created with correct content."""
        state = StateManager(
            ea_name='TestEA',
            ea_path='/path/to/TestEA.mq5',
            terminal='TestBroker',
            runs_dir=str(temp_dir),
        )

        content = json.loads(state.state_file.read_text())
        assert content['ea_name'] == 'TestEA'
        assert content['terminal'] == 'TestBroker'
        assert content['status'] == 'pending'

    def test_custom_workflow_id(self, temp_dir):
        """Test custom workflow ID."""
        state = StateManager(
            ea_name='TestEA',
            ea_path='/path/to/TestEA.mq5',
            terminal='TestBroker',
            workflow_id='custom_id_123',
            runs_dir=str(temp_dir),
        )

        assert state.workflow_id == 'custom_id_123'
        assert 'workflow_custom_id_123.json' in str(state.state_file)

    def test_symbol_timeframe(self, temp_dir):
        """Test symbol and timeframe are stored."""
        state = StateManager(
            ea_name='TestEA',
            ea_path='/path/to/TestEA.mq5',
            terminal='TestBroker',
            symbol='GBPUSD',
            timeframe='M15',
            runs_dir=str(temp_dir),
        )

        assert state.get('symbol') == 'GBPUSD'
        assert state.get('timeframe') == 'M15'


class TestStateManagerLoad:
    """Tests for loading existing state."""

    def test_load_existing(self, temp_dir):
        """Test loading existing state."""
        # Create state
        state1 = StateManager(
            ea_name='TestEA',
            ea_path='/path/to/TestEA.mq5',
            terminal='TestBroker',
            runs_dir=str(temp_dir),
        )
        workflow_id = state1.workflow_id

        # Load it
        state2 = StateManager.load(workflow_id, runs_dir=str(temp_dir))

        assert state2.workflow_id == workflow_id
        assert state2.get('ea_name') == 'TestEA'

    def test_load_not_found(self, temp_dir):
        """Test error when loading missing state."""
        with pytest.raises(FileNotFoundError):
            StateManager.load('nonexistent', runs_dir=str(temp_dir))

    def test_list_workflows(self, temp_dir):
        """Test listing workflows."""
        # Create multiple states
        StateManager('EA1', '/path/1', 'Term1', runs_dir=str(temp_dir))
        StateManager('EA2', '/path/2', 'Term2', runs_dir=str(temp_dir))

        workflows = StateManager.list_workflows(runs_dir=str(temp_dir))

        assert len(workflows) == 2
        names = [w['ea_name'] for w in workflows]
        assert 'EA1' in names
        assert 'EA2' in names


class TestStepManagement:
    """Tests for step management."""

    def test_start_step(self, temp_dir):
        """Test starting a step."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        state.start_step('1_load_ea')

        assert state.get('status') == 'in_progress'
        assert state.get('current_step') == 0
        step = state.state['steps']['1_load_ea']
        assert step['status'] == 'in_progress'
        assert 'started_at' in step

    def test_complete_step_pass(self, temp_dir):
        """Test completing a step with pass."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))
        state.start_step('1_load_ea')

        state.complete_step('1_load_ea', True, {'path': '/path'})

        step = state.state['steps']['1_load_ea']
        assert step['status'] == 'passed'
        assert step['result'] == {'path': '/path'}
        assert 'completed_at' in step

    def test_complete_step_fail(self, temp_dir):
        """Test completing a step with failure."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))
        state.start_step('1_load_ea')

        state.complete_step('1_load_ea', False, {}, 'File not found')

        step = state.state['steps']['1_load_ea']
        assert step['status'] == 'failed'
        assert step['error'] == 'File not found'
        assert state.get('status') == 'failed'

    def test_step_index(self, temp_dir):
        """Test getting step index."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        assert state.get_step_index('1_load_ea') == 0
        assert state.get_step_index('2_compile') == 3
        assert state.get_step_index('invalid') == -1

    def test_is_step_complete(self, temp_dir):
        """Test checking step completion."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        assert state.is_step_complete('1_load_ea') == False

        state.start_step('1_load_ea')
        assert state.is_step_complete('1_load_ea') == False

        state.complete_step('1_load_ea', True, {})
        assert state.is_step_complete('1_load_ea') == True

    def test_is_step_passed(self, temp_dir):
        """Test checking step passed."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))
        state.start_step('1_load_ea')

        state.complete_step('1_load_ea', True, {})
        assert state.is_step_passed('1_load_ea') == True

        state.start_step('2_compile')
        state.complete_step('2_compile', False, {})
        assert state.is_step_passed('2_compile') == False


class TestMetricsAndGates:
    """Tests for metrics and gates management."""

    def test_update_metrics(self, temp_dir):
        """Test updating metrics."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        state.update_metrics({'profit_factor': 2.0, 'max_drawdown_pct': 15.0})

        metrics = state.get('metrics')
        assert metrics['profit_factor'] == 2.0
        assert metrics['max_drawdown_pct'] == 15.0

    def test_update_gates(self, temp_dir):
        """Test updating gates."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        state.update_gates({
            'profit_factor': {'passed': True, 'value': 2.0, 'threshold': 1.5}
        })

        gates = state.get('gates')
        assert gates['profit_factor']['passed'] == True

    def test_all_gates_passed(self, temp_dir):
        """Test checking all gates passed."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        # No gates = True
        assert state.all_gates_passed() == True

        state.update_gates({'gate1': {'passed': True}})
        assert state.all_gates_passed() == True

        state.update_gates({'gate2': {'passed': False}})
        assert state.all_gates_passed() == False


class TestWorkflowCompletion:
    """Tests for workflow completion."""

    def test_complete_workflow_pass(self, temp_dir):
        """Test completing workflow with pass."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        state.complete_workflow(True)

        assert state.get('status') == 'completed'
        assert 'completed_at' in state.state

    def test_complete_workflow_fail(self, temp_dir):
        """Test completing workflow with failure."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        state.complete_workflow(False)

        assert state.get('status') == 'failed'


class TestSummary:
    """Tests for summary generation."""

    def test_get_summary(self, temp_dir):
        """Test getting workflow summary."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))
        state.start_step('1_load_ea')
        state.complete_step('1_load_ea', True, {})
        state.update_metrics({'profit_factor': 2.0})

        summary = state.get_summary()

        assert summary['ea_name'] == 'TestEA'
        assert summary['steps_passed'] == 1
        assert summary['steps_failed'] == 0
        assert summary['metrics']['profit_factor'] == 2.0

    def test_to_dict(self, temp_dir):
        """Test full state export."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        full = state.to_dict()

        assert 'workflow_id' in full
        assert 'ea_name' in full
        assert 'steps' in full
        assert 'metrics' in full
        assert 'gates' in full


class TestPersistence:
    """Tests for state persistence."""

    def test_state_saved_on_update(self, temp_dir):
        """Test state is saved after updates."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        state.update_metrics({'test': 123})

        # Read file directly
        content = json.loads(state.state_file.read_text())
        assert content['metrics']['test'] == 123

    def test_updated_at_changes(self, temp_dir):
        """Test updated_at timestamp changes."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))
        initial_time = state.get('updated_at')

        import time
        time.sleep(0.01)  # Small delay

        state.set('test', 'value')
        new_time = state.get('updated_at')

        assert new_time != initial_time
