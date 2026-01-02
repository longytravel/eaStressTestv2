"""
Integration Tests for EA Stress Test System

Tests the complete workflow without requiring actual MT5 terminal.
Mocks MT5-dependent operations while testing all Python logic.
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.terminals import TerminalRegistry
from engine.state import StateManager
from engine.gates import (
    check_go_live_ready,
    calculate_composite_score,
    diagnose_failure,
    check_all_backtest_gates,
    check_all_monte_carlo_gates,
)
from modules.params import extract_params
# NOTE: suggest_param_ranges removed - Claude /param-analyzer does this now
from modules.injector import create_modified_ea, has_ontester, has_safety_guards
from modules.monte_carlo import run_monte_carlo, calculate_risk_metrics
from reports.stats_schema import StatsReport, create_sample_report


class TestDiscoveryPhase:
    """Tests for the discovery phase of the orchestrator."""

    def test_terminal_discovery(self, sample_terminals_json, temp_dir):
        """Test discovering configured terminals."""
        registry = TerminalRegistry(str(sample_terminals_json))

        terminals = registry.list_terminals()

        assert len(terminals) >= 1
        assert any(t['name'] == 'TestBroker' for t in terminals)
        assert any(t['default'] for t in terminals)

    def test_ea_discovery(self, sample_terminals_json, temp_dir):
        """Test discovering EA files."""
        registry = TerminalRegistry(str(sample_terminals_json))

        # Create some EA files
        experts_path = temp_dir / "data" / "MQL5" / "Experts"
        (experts_path / "TrendFollower.mq5").touch()
        (experts_path / "Scalper.mq5").touch()

        eas = registry.find_eas()

        assert len(eas) == 2
        names = [ea['name'] for ea in eas]
        assert 'TrendFollower' in names
        assert 'Scalper' in names

    def test_recent_workflows(self, temp_dir):
        """Test listing recent workflow runs."""
        # Create some workflow states
        StateManager('EA1', '/path/1', 'Term1', runs_dir=str(temp_dir))
        StateManager('EA2', '/path/2', 'Term1', runs_dir=str(temp_dir))

        workflows = StateManager.list_workflows(runs_dir=str(temp_dir))

        assert len(workflows) == 2
        assert all('ea_name' in w for w in workflows)
        assert all('status' in w for w in workflows)


class TestConfigurationPhase:
    """Tests for configuration and validation."""

    def test_terminal_validation(self, sample_terminals_json, temp_dir):
        """Test terminal path validation."""
        registry = TerminalRegistry(str(sample_terminals_json))

        result = registry.validate_terminal('TestBroker')

        assert result['valid'] == True
        assert len(result['issues']) == 0

    def test_terminal_invalid(self, sample_terminals_json, temp_dir):
        """Test handling invalid terminal."""
        registry = TerminalRegistry(str(sample_terminals_json))

        result = registry.validate_terminal('AnotherBroker')

        assert result['valid'] == False
        assert len(result['issues']) > 0


class TestEAPreparation:
    """Tests for EA preparation (injection, compilation)."""

    def test_parameter_extraction(self, sample_ea_file):
        """Test extracting EA parameters."""
        params = extract_params(str(sample_ea_file))

        assert len(params) >= 4
        optimizable = [p for p in params if p['optimizable']]
        assert len(optimizable) >= 3  # Period, LotSize, StopLoss, TakeProfit

    # NOTE: test_parameter_range_suggestion removed - Claude /param-analyzer does this now

    def test_code_injection(self, sample_ea_file, temp_dir):
        """Test OnTester and safety injection."""
        result = create_modified_ea(str(sample_ea_file))

        assert result['success'] == True
        assert result['ontester_injected'] == True
        assert result['safety_injected'] == True

        content = Path(result['modified_path']).read_text()
        assert has_ontester(content)
        assert has_safety_guards(content)


class TestWorkflowExecution:
    """Tests for workflow execution logic."""

    def test_state_initialization(self, temp_dir):
        """Test workflow state initialization."""
        state = StateManager(
            ea_name='TestEA',
            ea_path='/path/TestEA.mq5',
            terminal='TestBroker',
            symbol='EURUSD',
            timeframe='H1',
            runs_dir=str(temp_dir),
        )

        assert state.get('status') == 'pending'
        assert state.get('ea_name') == 'TestEA'
        assert 'backtest_dates' in state.state

    def test_step_progression(self, temp_dir):
        """Test workflow step progression."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        # Simulate steps
        state.start_step('1_load_ea')
        state.complete_step('1_load_ea', True, {'path': '/path'})

        state.start_step('2_compile')
        state.complete_step('2_compile', True, {'exe_path': '/path.ex5'})

        summary = state.get_summary()
        assert summary['steps_passed'] == 2
        assert summary['steps_failed'] == 0

    def test_gate_updates(self, temp_dir):
        """Test updating gates during workflow."""
        state = StateManager('TestEA', '/path', 'Term1', runs_dir=str(temp_dir))

        state.update_gates({
            'profit_factor': {'passed': True, 'value': 2.0, 'threshold': 1.5},
            'max_drawdown': {'passed': True, 'value': 15.0, 'threshold': 30.0},
        })

        assert state.all_gates_passed() == True

        state.update_gates({
            'mc_confidence': {'passed': False, 'value': 50.0, 'threshold': 70.0},
        })

        assert state.all_gates_passed() == False


class TestResultsAnalysis:
    """Tests for results analysis and gate checking."""

    def test_backtest_gates_pass(self, sample_backtest_results):
        """Test backtest gates with passing results."""
        result = check_all_backtest_gates(sample_backtest_results)

        assert result['all_passed'] == True
        assert result['gates']['profit_factor']['passed'] == True
        assert result['gates']['max_drawdown']['passed'] == True

    def test_backtest_gates_fail(self, sample_backtest_results):
        """Test backtest gates with failing results."""
        sample_backtest_results['profit_factor'] = 1.2
        sample_backtest_results['max_drawdown_pct'] = 35.0

        result = check_all_backtest_gates(sample_backtest_results)

        assert result['all_passed'] == False

    def test_monte_carlo_gates(self, sample_trades):
        """Test Monte Carlo gates."""
        mc_result = run_monte_carlo(sample_trades, iterations=500)
        gates = check_all_monte_carlo_gates(mc_result)

        assert 'all_passed' in gates
        assert 'mc_confidence' in gates['gates']
        assert 'mc_ruin' in gates['gates']

    def test_composite_score(self, sample_backtest_results):
        """Test composite score calculation."""
        score = calculate_composite_score(sample_backtest_results)

        assert 0 <= score <= 10
        # Score should be reasonable for sample data
        assert score > 0


class TestGoLiveDecision:
    """Tests for go-live readiness decision."""

    def test_go_live_ready(self):
        """Test go-live with all gates passing."""
        state = {
            'gates': {
                'profit_factor': {'passed': True},
                'max_drawdown': {'passed': True},
                'minimum_trades': {'passed': True},
                'mc_confidence': {'passed': True},
                'mc_ruin': {'passed': True},
            }
        }

        result = check_go_live_ready(state)

        assert result['go_live_ready'] == True
        assert 'READY' in result['message']

    def test_go_live_not_ready(self):
        """Test go-live with failing gates."""
        state = {
            'gates': {
                'profit_factor': {'passed': False, 'value': 1.2, 'threshold': 1.5},
                'max_drawdown': {'passed': True},
                'minimum_trades': {'passed': True},
                'mc_confidence': {'passed': True},
                'mc_ruin': {'passed': True},
            }
        }

        result = check_go_live_ready(state)

        assert result['go_live_ready'] == False
        assert 'NOT' in result['message']


class TestFailureDiagnosis:
    """Tests for failure diagnosis."""

    def test_diagnose_pf_failure(self):
        """Test diagnosis of profit factor failure."""
        gates = {
            'profit_factor': {
                'passed': False,
                'value': 1.2,
                'threshold': 1.5,
                'operator': '>=',
            }
        }
        metrics = {'avg_win': 40, 'avg_loss': 35, 'win_rate': 55}

        diagnoses = diagnose_failure(gates, metrics)

        assert len(diagnoses) == 1
        assert 'PF' in diagnoses[0] or '1.2' in diagnoses[0]

    def test_diagnose_multiple_failures(self):
        """Test diagnosis of multiple failures."""
        gates = {
            'profit_factor': {'passed': False, 'value': 1.2, 'threshold': 1.5, 'operator': '>='},
            'max_drawdown': {'passed': False, 'value': 35, 'threshold': 30, 'operator': '<='},
            'mc_ruin': {'passed': False, 'value': 10, 'threshold': 5, 'operator': '<='},
        }

        diagnoses = diagnose_failure(gates, {'avg_win': 40, 'avg_loss': 35})

        assert len(diagnoses) == 3


class TestReportGeneration:
    """Tests for report and stats generation."""

    def test_sample_report_creation(self):
        """Test creating a sample stats report."""
        report = create_sample_report()

        assert report.ea_name != ''
        assert report.composite_score > 0
        assert report.go_live_ready == True
        assert len(report.gates) > 0

    def test_report_serialization(self):
        """Test report can be serialized to JSON."""
        report = create_sample_report()
        d = report.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(d, default=str)
        parsed = json.loads(json_str)

        assert parsed['ea_name'] == report.ea_name
        assert parsed['composite_score'] == report.composite_score

    def test_report_insights(self):
        """Test report contains insights."""
        report = create_sample_report()

        assert report.edge_summary != ''
        assert len(report.weaknesses) > 0
        assert len(report.recommendations) > 0


class TestFullWorkflowSimulation:
    """Full workflow simulation without MT5."""

    def test_complete_workflow_pass(self, temp_dir, sample_ea_file, sample_trades):
        """Simulate a complete passing workflow."""
        # 1. Initialize state
        state = StateManager(
            ea_name='TestEA',
            ea_path=str(sample_ea_file),
            terminal='TestBroker',
            runs_dir=str(temp_dir),
        )

        # 2. Step 1: Load EA
        state.start_step('1_load_ea')
        state.complete_step('1_load_ea', True, {'path': str(sample_ea_file)})

        # 3. Step 1B/1C: Injection
        result = create_modified_ea(str(sample_ea_file))
        state.start_step('1b_inject_ontester')
        state.complete_step('1b_inject_ontester', True, result)

        # 4. Step 2: Compile (mocked)
        state.start_step('2_compile')
        state.complete_step('2_compile', True, {'exe_path': '/fake/path.ex5'})

        # 5. Step 3: Extract params
        params = extract_params(str(sample_ea_file))
        state.start_step('3_extract_params')
        state.complete_step('3_extract_params', True, {'params': params})

        # 6. Step 4: Analyze params (Claude /param-analyzer does this - mocked here)
        mock_ranges = [
            {'name': 'Period', 'start': 5, 'stop': 50, 'step': 5},
            {'name': 'LotSize', 'start': 0.01, 'stop': 0.1, 'step': 0.01},
        ]
        state.start_step('4_analyze_params')
        state.complete_step('4_analyze_params', True, {'ranges': mock_ranges})

        # 7. Step 5: Validate trades (mocked)
        state.start_step('5_validate_trades')
        state.complete_step('5_validate_trades', True, {'total_trades': 120})
        state.update_gates({'minimum_trades': {'passed': True, 'value': 120, 'threshold': 50}})

        # 8. Steps 6-8: Optimization (mocked)
        state.start_step('7_run_optimization')
        state.complete_step('7_run_optimization', True, {'passes': 500})
        state.update_gates({'optimization_passes': {'passed': True, 'value': 500}})

        # 9. Step 9: Backtest robust (mocked with good results)
        backtest_results = {
            'profit': 5000,
            'profit_factor': 2.1,
            'max_drawdown_pct': 18.5,
            'total_trades': 120,
            'win_rate': 62,
        }
        state.start_step('9_backtest_robust')
        state.complete_step('9_backtest_robust', True, backtest_results)
        state.update_metrics(backtest_results)

        gates = check_all_backtest_gates(backtest_results)
        for name, gate in gates['gates'].items():
            state.update_gates({name: gate})

        # 10. Step 10: Monte Carlo
        mc_result = run_monte_carlo(sample_trades, iterations=1000)
        state.start_step('10_monte_carlo')
        state.complete_step('10_monte_carlo', True, mc_result)

        mc_gates = check_all_monte_carlo_gates(mc_result)
        for name, gate in mc_gates['gates'].items():
            state.update_gates({name: gate})

        # 11. Step 11: Generate reports
        state.start_step('11_generate_reports')
        score = calculate_composite_score(state.get('metrics', {}))
        state.set('composite_score', score)

        go_live = check_go_live_ready(state.to_dict())
        state.set('go_live', go_live)
        state.complete_step('11_generate_reports', True, {'score': score})

        # Complete workflow
        state.complete_workflow(True)

        # Verify final state
        summary = state.get_summary()
        assert summary['status'] == 'completed'
        assert summary['steps_passed'] >= 10
        assert summary['steps_failed'] == 0

    def test_complete_workflow_fail(self, temp_dir, sample_ea_file):
        """Simulate a failing workflow."""
        state = StateManager(
            ea_name='FailingEA',
            ea_path=str(sample_ea_file),
            terminal='TestBroker',
            runs_dir=str(temp_dir),
        )

        # Simulate steps up to validation failure
        state.start_step('1_load_ea')
        state.complete_step('1_load_ea', True, {})

        state.start_step('5_validate_trades')
        state.complete_step('5_validate_trades', False, {'total_trades': 20})
        state.update_gates({'minimum_trades': {'passed': False, 'value': 20, 'threshold': 50}})

        state.complete_workflow(False)

        # Verify failure state
        summary = state.get_summary()
        assert summary['status'] == 'failed'
        assert summary['steps_failed'] >= 1
        assert state.all_gates_passed() == False

        # Verify diagnosis available
        diagnoses = diagnose_failure(
            state.get('gates', {}),
            state.get('metrics', {}),
        )
        # Should have diagnosis for minimum_trades failure
        assert len(diagnoses) >= 1


class TestSkillsIntegration:
    """Tests for skills integration points."""

    def test_param_analyzer_input(self, sample_ea_file):
        """Test param-analyzer receives correct input."""
        params = extract_params(str(sample_ea_file))
        optimizable = [p for p in params if p['optimizable']]

        # param-analyzer would receive this
        assert len(optimizable) >= 3
        for p in optimizable:
            assert 'name' in p
            assert 'type' in p
            assert 'default' in p

    def test_stats_analyzer_input(self, sample_backtest_results, sample_trades):
        """Test stats-analyzer receives correct input."""
        mc_result = run_monte_carlo(sample_trades, iterations=500)
        risk_metrics = calculate_risk_metrics(sample_trades)

        # stats-analyzer would receive this data
        input_data = {
            'backtest': sample_backtest_results,
            'monte_carlo': mc_result,
            'risk_metrics': risk_metrics,
        }

        assert 'profit_factor' in input_data['backtest']
        assert 'confidence' in input_data['monte_carlo']
        assert 'sharpe_ratio' in input_data['risk_metrics']

    def test_ea_improver_input(self):
        """Test ea-improver receives correct input."""
        report = create_sample_report()

        # ea-improver would receive the stats report
        assert len(report.weaknesses) > 0
        assert len(report.recommendations) > 0
        assert report.fragile_params is not None
