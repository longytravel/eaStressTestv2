"""
Workflow Runner

Orchestrates the 11-step EA stress test workflow.
Each step has a gate that must pass before proceeding.
"""
from pathlib import Path
from typing import Optional, Callable
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.state import StateManager
from engine.terminals import TerminalRegistry
from engine import gates

# Direct module loading to avoid circular imports through modules/__init__.py
from modules.loader import load_module, get_modules_dir

_modules_dir = get_modules_dir()

_compiler = load_module("compiler", _modules_dir / "compiler.py")
compile_ea = _compiler.compile_ea

_params = load_module("params", _modules_dir / "params.py")
extract_params = _params.extract_params

_injector = load_module("injector", _modules_dir / "injector.py")
create_modified_ea = _injector.create_modified_ea

_backtest = load_module("backtest", _modules_dir / "backtest.py")
run_backtest = _backtest.run_backtest

_optimizer = load_module("optimizer", _modules_dir / "optimizer.py")
run_optimization = _optimizer.run_optimization
parse_optimization_results = _optimizer.parse_optimization_results
# NOTE: find_robust_params was REMOVED - Claude's /stats-analyzer selects passes now

_monte_carlo = load_module("monte_carlo", _modules_dir / "monte_carlo.py")
run_monte_carlo = _monte_carlo.run_monte_carlo
extract_trades_from_results = _monte_carlo.extract_trades_from_results

# NOTE: Parameter analysis is done by Claude via /param-analyzer skill
# No Python heuristics - Claude's intelligence is required
import settings


class WorkflowRunner:
    """
    Runs the 11-step stress test workflow.

    Steps:
    1. Load EA - verify file exists
    1B. Inject OnTester - add optimization criterion function
    1C. Inject Safety - add safety guards
    2. Compile - compile the modified EA
    3. Extract Params - parse input parameters
        ↓ PAUSE: awaiting_param_analysis
    4. Analyze Params - Claude /param-analyzer generates WIDE params + opt ranges
    5. Validate Trades - quick backtest to verify trading activity
    5B. [If fails] PAUSE: awaiting_ea_fix - Claude /mql5-fixer diagnoses
    6. Create INI - generate optimization config
    7. Run Optimization - run genetic optimization
    8. Parse Results - raw results only
        ↓ PAUSE: awaiting_stats_analysis
    8B. Stats Analysis - Claude /stats-analyzer selects top 20, explains why
    9. Backtest Top 20 - backtest Claude's selected passes
    10. Monte Carlo - simulate robustness
    11. Generate Reports - create dashboard + update leaderboard
        ═══════════════════════════════════════
        WORKFLOW COMPLETE

    --- USER-INITIATED IMPROVEMENT LOOP (Optional) ---
    User invokes /ea-improver → suggests code fixes
    User approves → /mql5-fixer applies changes
    restart_with_improved_ea() → Full restart from Step 1
    """

    def __init__(
        self,
        ea_path: str,
        terminal_name: Optional[str] = None,
        symbol: str = 'EURUSD',
        timeframe: str = 'H1',
        on_step_complete: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ):
        """
        Initialize workflow runner.

        Args:
            ea_path: Path to the .mq5 EA file
            terminal_name: Name of terminal to use (from registry)
            symbol: Trading symbol
            timeframe: Timeframe string
            on_step_complete: Callback(step_name, passed, result) after each step
            on_progress: Callback(message) for progress updates
        """
        self.ea_path = Path(ea_path)
        self.symbol = symbol
        self.timeframe = timeframe
        self.on_step_complete = on_step_complete
        self.on_progress = on_progress

        # Setup terminal
        self.registry = TerminalRegistry()
        if terminal_name:
            self.registry.set_active(terminal_name)
        self.terminal = self.registry.get_terminal()

        # Initialize state
        self.state = StateManager(
            ea_name=self.ea_path.stem,
            ea_path=str(self.ea_path),
            terminal=self.terminal['name'],
            symbol=symbol,
            timeframe=timeframe,
        )

        # Working paths
        self.modified_ea_path = None
        self.compiled_ea_path = None
        self.params = []
        self.param_ranges = []
        self.wide_validation_params = {}  # Wide params for Step 5 validation
        self.optimization_results = None
        self.selected_passes = []  # Top 20 passes selected by Claude /stats-analyzer
        self.stats_analysis = {}  # Claude's analysis report
        self.backtest_results = {}
        self.top20_backtest_results = []  # Top 20 passes backtested for leaderboard
        self.mc_results = {}

        # Improvement loop tracking
        self.previous_workflow_id = None  # Link to previous run if this is an improvement

        # Step 5B: EA Fix tracking
        self.fix_attempts = 0
        self.max_fix_attempts = 3
        self.original_ea_backed_up = False
        self.original_ea_path = None  # Path to backup

    def _log(self, message: str) -> None:
        """Send progress message."""
        if self.on_progress:
            self.on_progress(message)

    def _get_results_dir(self) -> Path:
        """Get the directory for storing large result files."""
        results_dir = Path(settings.RUNS_DIR) / self.state.workflow_id
        results_dir.mkdir(parents=True, exist_ok=True)
        return results_dir

    def _save_results(self, name: str, data: dict) -> str:
        """Save large results to a separate JSON file."""
        import json
        results_dir = self._get_results_dir()
        file_path = results_dir / f"{name}.json"
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return str(file_path)

    def _load_results(self, name: str) -> dict:
        """Load results from a separate JSON file."""
        import json
        results_dir = self._get_results_dir()
        file_path = results_dir / f"{name}.json"
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        return {}

    def _restore_paths_from_state(self) -> None:
        """Restore working paths from step results when loading existing workflow."""
        steps = self.state.state.get('steps', {})

        # Restore modified EA path from step 1b
        step_1b = steps.get('1b_inject_ontester', {}).get('result', {})
        if step_1b.get('modified_path'):
            self.modified_ea_path = step_1b['modified_path']

        # Restore compiled EA path from step 2
        step_2 = steps.get('2_compile', {}).get('result', {})
        if step_2.get('exe_path'):
            self.compiled_ea_path = step_2['exe_path']

        # Restore params from step 3
        step_3 = steps.get('3_extract_params', {}).get('result', {})
        if step_3.get('params'):
            self.params = step_3['params']

        # Restore optimization ranges and wide params from step 4 if available
        step_4 = steps.get('4_analyze_params', {}).get('result', {})
        if step_4.get('optimization_ranges'):
            self.param_ranges = step_4['optimization_ranges']
        if step_4.get('wide_validation_params'):
            self.wide_validation_params = step_4['wide_validation_params']

        # Restore optimization results from disk (large file)
        step_7 = steps.get('7_run_optimization', {}).get('result', {})
        if step_7.get('results_file'):
            self.optimization_results = self._load_results('optimization')
        elif step_7.get('results'):
            # Fallback for legacy runs stored inline
            self.optimization_results = step_7

        # Restore selected passes and analysis from step 8b if available
        step_8b = steps.get('8b_stats_analysis', {}).get('result', {})
        if step_8b.get('selected_passes'):
            self.selected_passes = step_8b['selected_passes']
        if step_8b.get('analysis'):
            self.stats_analysis = step_8b['analysis']

        # Restore backtest results from disk (large file)
        step_9 = steps.get('9_backtest_robust', {}).get('result', {})
        if step_9.get('results_file'):
            backtest_data = self._load_results('backtests')
            self.top20_backtest_results = backtest_data.get('all_results', [])
            self.backtest_results = backtest_data.get('best_result', {})

        # Restore previous workflow link if this is an improvement run
        if self.state.get('previous_workflow_id'):
            self.previous_workflow_id = self.state.get('previous_workflow_id')

    def _step_done(self, step_name: str, passed: bool, result: dict) -> None:
        """Handle step completion."""
        self.state.complete_step(step_name, passed, result)
        if self.on_step_complete:
            self.on_step_complete(step_name, passed, result)

    def run(self, stop_on_failure: bool = True, pause_for_analysis: bool = True) -> dict:
        """
        Run the complete workflow.

        Args:
            stop_on_failure: If True, stop at first failed gate
            pause_for_analysis: If True, pause after Step 3 for Claude to analyze params

        Returns:
            Final workflow state summary (or partial if paused)
        """
        self.state.set_status('in_progress')

        # Phase 1: Steps 1-3 (preparation)
        phase1_steps = [
            ('1_load_ea', self._step_load_ea),
            ('1b_inject_ontester', self._step_inject_ontester),
            ('1c_inject_safety', self._step_inject_safety),
            ('2_compile', self._step_compile),
            ('3_extract_params', self._step_extract_params),
        ]

        for step_name, step_func in phase1_steps:
            self._log(f"Starting step: {step_name}")
            self.state.start_step(step_name)

            try:
                passed, result = step_func()
            except Exception as e:
                passed = False
                result = {'error': str(e)}
                self.state.complete_step(step_name, False, result, str(e))

            self._step_done(step_name, passed, result)

            if not passed:
                self._log(f"Step {step_name} FAILED")
                if stop_on_failure:
                    self.state.complete_workflow(False)
                    return self.state.get_summary()

            self._log(f"Step {step_name} PASSED")

        # If pause_for_analysis, return here so Claude can analyze params
        if pause_for_analysis:
            self.state.set_status('awaiting_param_analysis')
            self._log("PAUSED: Awaiting Claude parameter analysis (call continue_with_params)")
            return self.state.get_summary()

        # Otherwise, continue with automated flow (not recommended)
        return self._continue_automated(stop_on_failure)

    def continue_with_params(
        self,
        wide_validation_params: dict,
        optimization_ranges: list[dict],
        stop_on_failure: bool = True
    ) -> dict:
        """
        Continue workflow from Step 4 with Claude-analyzed parameters.

        This should be called after Claude has intelligently analyzed the
        extracted parameters and generated:
        1. wide_validation_params - Params to maximize trades for validation
        2. optimization_ranges - Intelligent ranges for optimization

        Args:
            wide_validation_params: Dict of {param_name: value} for validation backtest
            optimization_ranges: List of param dicts with start/step/stop for optimization
            stop_on_failure: If True, stop at first failed gate

        Returns:
            Final workflow state summary
        """
        # Restore paths from previous steps if continuing from loaded state
        self._restore_paths_from_state()

        # Store the Claude-analyzed params
        self.wide_validation_params = wide_validation_params
        self.param_ranges = optimization_ranges

        self.state.set_status('in_progress')

        # Mark Step 4 as passed with Claude's analysis
        self._log("Starting step: 4_analyze_params (Claude-analyzed)")
        self.state.start_step('4_analyze_params')
        self._step_done('4_analyze_params', True, {
            'source': 'claude_analysis',
            'wide_validation_params': wide_validation_params,
            'wide_param_count': len(wide_validation_params),
            'optimization_ranges': optimization_ranges,
            'optimization_param_count': len(optimization_ranges),
        })
        self._log("Step 4_analyze_params PASSED (Claude-analyzed)")

        # Continue with Phase 2
        return self._run_phase2(stop_on_failure)

    def _continue_automated(self, stop_on_failure: bool = True) -> dict:
        """
        DEPRECATED: Do not use automated param analysis.

        Parameter analysis MUST be done by Claude via /param-analyzer skill.
        This method exists only for backwards compatibility and will error.
        """
        raise NotImplementedError(
            "Automated parameter analysis is disabled. "
            "Use continue_with_params() with Claude-analyzed parameters. "
            "Invoke /param-analyzer skill to generate wide_params and opt_ranges."
        )

    def _run_phase2(self, stop_on_failure: bool = True) -> dict:
        """Run Phase 2 steps (5-11) after params are set."""

        # Step 5: Validate Trades
        self._log("Starting step: 5_validate_trades")
        self.state.start_step('5_validate_trades')

        try:
            passed, result = self._step_validate_trades()
        except Exception as e:
            passed = False
            result = {'error': str(e)}
            self.state.complete_step('5_validate_trades', False, result, str(e))

        self._step_done('5_validate_trades', passed, result)

        if not passed:
            self._log("Step 5_validate_trades FAILED")

            # Check if we can attempt a fix
            if self.fix_attempts < self.max_fix_attempts:
                self.fix_attempts += 1
                self.state.set('fix_attempts', self.fix_attempts)
                self.state.set('max_fix_attempts', self.max_fix_attempts)
                self.state.set_status('awaiting_ea_fix')

                self._log(f"PAUSED: Awaiting EA fix (attempt {self.fix_attempts}/{self.max_fix_attempts})")
                self._log("Invoke /mql5-fixer skill to diagnose and fix the EA")

                return self.state.get_summary()
            else:
                self._log(f"Max fix attempts ({self.max_fix_attempts}) reached - workflow failed")
                self.state.complete_workflow(False)
                return self.state.get_summary()

        self._log("Step 5_validate_trades PASSED")

        # Continue with Steps 6-11
        return self._run_phase3(stop_on_failure)

    def _run_phase3(self, stop_on_failure: bool = True) -> dict:
        """Run Phase 3a steps (6-8) - optimization then pause for Claude analysis."""
        phase3a_steps = [
            ('6_create_ini', self._step_create_ini),
            ('7_run_optimization', self._step_run_optimization),
            ('8_parse_results', self._step_parse_results),
        ]

        for step_name, step_func in phase3a_steps:
            self._log(f"Starting step: {step_name}")
            self.state.start_step(step_name)

            try:
                passed, result = step_func()
            except Exception as e:
                passed = False
                result = {'error': str(e)}
                self.state.complete_step(step_name, False, result, str(e))

            self._step_done(step_name, passed, result)

            if not passed:
                self._log(f"Step {step_name} FAILED")
                if stop_on_failure:
                    self.state.complete_workflow(False)
                    return self.state.get_summary()

            self._log(f"Step {step_name} PASSED")

        # PAUSE for Claude /stats-analyzer to analyze and select top 20 passes
        self.state.set_status('awaiting_stats_analysis')
        self._log("PAUSED: Awaiting Claude stats analysis (call continue_with_analysis)")
        self._log("Invoke /stats-analyzer skill to analyze passes and select top 20")
        return self.state.get_summary()

    def continue_with_analysis(
        self,
        selected_passes: list[dict],
        analysis: dict,
        stop_on_failure: bool = True
    ) -> dict:
        """
        Continue workflow from Step 8B with Claude-analyzed passes.

        This should be called after Claude has analyzed optimization results
        with /stats-analyzer and selected the top 20 passes to backtest.

        Args:
            selected_passes: List of pass dicts selected by Claude (max 20)
            analysis: Claude's analysis dict with reasoning, insights, etc.
            stop_on_failure: If True, stop at first failed gate

        Returns:
            Final workflow state summary
        """
        # Restore paths from previous steps if continuing from loaded state
        self._restore_paths_from_state()

        # Store Claude's selections
        self.selected_passes = selected_passes[:20]  # Limit to 20
        self.stats_analysis = analysis

        self.state.set_status('in_progress')

        # Mark Step 8B as passed with Claude's analysis
        self._log("Starting step: 8b_stats_analysis (Claude-analyzed)")
        self.state.start_step('8b_stats_analysis')
        self._step_done('8b_stats_analysis', True, {
            'source': 'claude_analysis',
            'selected_passes': self.selected_passes,
            'selected_count': len(self.selected_passes),
            'analysis': analysis,
        })
        self._log("Step 8b_stats_analysis PASSED (Claude-analyzed)")

        # Continue with Phase 3b (Steps 9-11)
        return self._run_phase3b(stop_on_failure)

    def _run_phase3b(self, stop_on_failure: bool = True) -> dict:
        """Run Phase 3b steps (9-11) after Claude selects passes.

        Note: Step 11 (generate_reports) ALWAYS runs regardless of stop_on_failure,
        so users always see dashboards even when gates fail.
        """
        phase3b_steps = [
            ('9_backtest_robust', self._step_backtest_robust),
            ('10_monte_carlo', self._step_monte_carlo),
            ('11_generate_reports', self._step_generate_reports),
        ]

        all_passed = True
        should_skip = False  # Track if we should skip to Step 11

        for step_name, step_func in phase3b_steps:
            # Step 11 (generate_reports) ALWAYS runs - users need dashboards
            if should_skip and step_name != '11_generate_reports':
                self._log(f"Skipping step: {step_name} (previous step failed)")
                continue

            self._log(f"Starting step: {step_name}")
            self.state.start_step(step_name)

            try:
                passed, result = step_func()
            except Exception as e:
                passed = False
                result = {'error': str(e)}
                self.state.complete_step(step_name, False, result, str(e))

            self._step_done(step_name, passed, result)

            if not passed:
                all_passed = False
                self._log(f"Step {step_name} FAILED")
                # Don't break - skip to Step 11 instead
                if stop_on_failure and step_name != '11_generate_reports':
                    should_skip = True
            else:
                self._log(f"Step {step_name} PASSED")

        # Complete workflow
        self.state.complete_workflow(all_passed)

        # Calculate score and go-live status (even for partial success)
        score = gates.calculate_composite_score(self.state.get('metrics', {}))
        self.state.set('composite_score', score)

        # Check go-live readiness
        go_live = gates.check_go_live_ready(self.state.to_dict())
        self.state.set('go_live', go_live)

        return self.state.get_summary()

    def backup_original_ea(self) -> str:
        """
        Backup the original EA before making fixes.

        Returns:
            Path to the backup file
        """
        if self.original_ea_backed_up:
            return self.original_ea_path

        import shutil
        backup_path = self.ea_path.parent / f"{self.ea_path.stem}_original{self.ea_path.suffix}"
        shutil.copy2(self.ea_path, backup_path)

        self.original_ea_backed_up = True
        self.original_ea_path = str(backup_path)
        self.state.set('original_ea_backup', self.original_ea_path)

        self._log(f"Original EA backed up to: {backup_path}")
        return self.original_ea_path

    def restart_after_fix(self) -> dict:
        """
        Restart workflow from Step 1 after EA has been fixed.

        This should be called after Claude has:
        1. Diagnosed the issue with /mql5-fixer
        2. Asked user permission
        3. Modified the EA
        4. Backed up the original (call backup_original_ea() first)

        Returns:
            Workflow state summary
        """
        if self.state.get('status') != 'awaiting_ea_fix':
            raise RuntimeError(
                "Cannot restart - workflow is not awaiting EA fix. "
                f"Current status: {self.state.get('status')}"
            )

        self._log(f"Restarting workflow after fix (attempt {self.fix_attempts}/{self.max_fix_attempts})")
        self.state.set_status('in_progress')

        # Clear previous step results but keep fix tracking
        self.modified_ea_path = None
        self.compiled_ea_path = None
        self.params = []
        self.param_ranges = []
        self.wide_validation_params = {}

        # Re-run from Step 1
        return self.run(pause_for_analysis=True)

    def restart_with_improved_ea(self) -> 'WorkflowRunner':
        """
        Start fresh workflow with improved EA after user-initiated improvement.

        This should be called after:
        1. User reviewed dashboard and invoked /ea-improver
        2. Claude suggested improvements
        3. User approved the changes
        4. Changes applied via /mql5-fixer
        5. Original EA backed up

        Returns:
            New WorkflowRunner instance for the improved EA
        """
        # Store reference to this workflow for comparison
        previous_workflow_id = self.state.workflow_id

        # The EA path should still point to the same file (which is now modified)
        improved_ea_path = str(self.ea_path)

        self._log(f"Starting improvement run for {self.ea_path.stem}")
        self._log(f"Previous workflow: {previous_workflow_id}")

        # Create new runner for the improved EA
        new_runner = WorkflowRunner(
            ea_path=improved_ea_path,
            terminal_name=self.terminal['name'],
            symbol=self.symbol,
            timeframe=self.timeframe,
            on_step_complete=self.on_step_complete,
            on_progress=self.on_progress,
        )

        # Link to previous workflow
        new_runner.previous_workflow_id = previous_workflow_id
        new_runner.state.set('previous_workflow_id', previous_workflow_id)
        new_runner.state.set('improvement_run', True)

        return new_runner

    @classmethod
    def from_workflow_id(cls, workflow_id: str, runs_dir: str = None) -> 'WorkflowRunner':
        """
        Load an existing workflow and create a runner to continue it.

        Args:
            workflow_id: The workflow ID to load
            runs_dir: Optional runs directory path

        Returns:
            WorkflowRunner instance configured to continue the workflow
        """
        # Load the state
        state = StateManager.load(workflow_id, runs_dir)

        # Create runner without full init
        runner = cls.__new__(cls)

        # Set basic attributes from state
        runner.ea_path = Path(state.get('ea_path'))
        runner.symbol = state.get('symbol', 'EURUSD')
        runner.timeframe = state.get('timeframe', 'H1')
        runner.on_step_complete = None
        runner.on_progress = None

        # Setup terminal
        runner.registry = TerminalRegistry()
        terminal_name = state.get('terminal')
        if terminal_name:
            runner.registry.set_active(terminal_name)
        runner.terminal = runner.registry.get_terminal()

        # Use existing state
        runner.state = state

        # Initialize working variables
        runner.modified_ea_path = None
        runner.compiled_ea_path = None
        runner.params = []
        runner.param_ranges = []
        runner.wide_validation_params = {}
        runner.optimization_results = None
        runner.selected_passes = []
        runner.stats_analysis = {}
        runner.backtest_results = {}
        runner.top20_backtest_results = []
        runner.mc_results = {}
        runner.previous_workflow_id = None

        # Fix tracking
        runner.fix_attempts = state.get('fix_attempts', 0)
        runner.max_fix_attempts = state.get('max_fix_attempts', 3)
        runner.original_ea_backed_up = state.get('original_ea_backup') is not None
        runner.original_ea_path = state.get('original_ea_backup')

        # Restore all paths from state
        runner._restore_paths_from_state()

        return runner

    # =========================================================================
    # Step Implementations
    # =========================================================================

    def _step_load_ea(self) -> tuple[bool, dict]:
        """Step 1: Verify EA file exists."""
        gate = gates.check_file_exists(str(self.ea_path))

        return gate.passed, {
            'path': str(self.ea_path),
            'exists': gate.passed,
            'gate': gate.to_dict(),
        }

    def _step_inject_ontester(self) -> tuple[bool, dict]:
        """Step 1B: Inject OnTester function."""
        result = create_modified_ea(
            str(self.ea_path),
            inject_tester=True,
            inject_guards=False,
        )

        if result['success']:
            self.modified_ea_path = result['modified_path']

        return result['success'], result

    def _step_inject_safety(self) -> tuple[bool, dict]:
        """Step 1C: Inject safety guards."""
        if not self.modified_ea_path:
            return False, {'error': 'No modified EA from previous step'}

        # Read current modified content and add safety
        from modules.injector import inject_safety
        content = Path(self.modified_ea_path).read_text(encoding='utf-8')
        content, injected = inject_safety(content)
        Path(self.modified_ea_path).write_text(content, encoding='utf-8')

        return True, {'safety_injected': injected, 'path': self.modified_ea_path}

    def _step_compile(self) -> tuple[bool, dict]:
        """Step 2: Compile the EA."""
        ea_to_compile = self.modified_ea_path or str(self.ea_path)

        result = compile_ea(ea_to_compile, terminal=self.terminal)
        gate = gates.check_compilation(result)

        if result['success']:
            self.compiled_ea_path = result['exe_path']

        self.state.update_gates({'compilation': gate.to_dict()})

        return gate.passed, {**result, 'gate': gate.to_dict()}

    def _step_extract_params(self) -> tuple[bool, dict]:
        """Step 3: Extract input parameters."""
        try:
            self.params = extract_params(str(self.ea_path))
        except Exception as e:
            return False, {'error': str(e)}

        gate = gates.check_params_found(self.params)
        self.state.update_gates({'params_found': gate.to_dict()})

        return gate.passed, {
            'params': self.params,
            'count': len(self.params),
            'optimizable': sum(1 for p in self.params if p.get('optimizable')),
            'gate': gate.to_dict(),
        }

    # NOTE: _step_analyze_params is REMOVED
    # Step 4 is handled by Claude via /param-analyzer skill
    # Claude calls continue_with_params() with analyzed parameters

    def _step_validate_trades(self) -> tuple[bool, dict]:
        """Step 5: Quick backtest to verify trading activity."""
        if not self.compiled_ea_path:
            return False, {'error': 'No compiled EA'}

        # Run a quick backtest with WIDE params (not defaults!)
        # Wide params are designed to maximize trade count to prove EA can trade
        result = run_backtest(
            self.compiled_ea_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            terminal=self.terminal,
            params=self.wide_validation_params if self.wide_validation_params else None,
        )

        if not result.get('success'):
            return False, result

        trades = result.get('total_trades', 0)
        gate = gates.check_minimum_trades(trades)
        self.state.update_gates({'minimum_trades': gate.to_dict()})

        return gate.passed, {**result, 'gate': gate.to_dict()}

    def _step_create_ini(self) -> tuple[bool, dict]:
        """Step 6: Create optimization INI file."""
        from modules.optimizer import create_ini_file

        try:
            ini_path = create_ini_file(
                ea_name=Path(self.compiled_ea_path).name,
                symbol=self.symbol,
                timeframe=self.timeframe,
                param_ranges=self.param_ranges,
                terminal=self.terminal,
            )
            return True, {'ini_path': ini_path}
        except Exception as e:
            return False, {'error': str(e)}

    def _step_run_optimization(self) -> tuple[bool, dict]:
        """Step 7: Run optimization."""
        if not self.compiled_ea_path:
            return False, {'error': 'No compiled EA'}

        result = run_optimization(
            self.compiled_ea_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            param_ranges=self.param_ranges,
            terminal=self.terminal,
        )

        if result.get('success'):
            self.optimization_results = result
            # Save full results to disk (can be 8000+ passes)
            results_file = self._save_results('optimization', result)
            self._log(f"Optimization results saved to: {results_file}")

        passes = result.get('passes', 0)
        gate = gates.check_optimization_passes(passes)
        self.state.update_gates({'optimization_passes': gate.to_dict()})

        # Return summary only (not full results - they're on disk)
        summary = {
            'success': result.get('success'),
            'passes': passes,
            'results_file': results_file if result.get('success') else None,
            'gate': gate.to_dict(),
        }
        return gate.passed, summary

    def _step_parse_results(self) -> tuple[bool, dict]:
        """Step 8: Parse optimization results (raw data for Claude to analyze)."""
        if not self.optimization_results:
            return False, {'error': 'No optimization results'}

        results = self.optimization_results.get('results', [])

        # Basic filtering - just check we have valid passes
        # Claude's /stats-analyzer will do intelligent selection
        valid_count = sum(1 for r in results if r.get('total_trades', 0) >= settings.MIN_TRADES)

        if valid_count == 0:
            return False, {
                'error': f'No passes meet minimum trade threshold ({settings.MIN_TRADES})',
                'total_passes': len(results),
                'valid_passes': 0,
            }

        # Store results for Claude to analyze
        # NOTE: Full results are stored in optimization_results from Step 7
        # Claude will invoke /stats-analyzer to select top 20

        return True, {
            'total_passes': len(results),
            'valid_passes': valid_count,
            'message': 'Results parsed. Invoke /stats-analyzer to select top 20 passes.',
        }

    def _step_backtest_robust(self) -> tuple[bool, dict]:
        """Step 9: Backtest top 20 passes selected by Claude."""
        if not self.compiled_ea_path:
            return False, {'error': 'No compiled EA'}

        # Get passes selected by Claude via /stats-analyzer
        top_passes = self.selected_passes
        if not top_passes:
            return False, {'error': 'No passes selected. Did you invoke /stats-analyzer?'}

        # Fields that are optimization results, NOT input parameters
        RESULT_FIELDS = {
            'Pass', 'Result', 'Forward Result', 'Back Result', 'Custom',
            'Profit', 'Profit Factor', 'Expected Payoff', 'Recovery Factor',
            'Sharpe Ratio', 'Equity DD %', 'Trades',
        }

        # Get fixed params (e.g., slope filter disable) from param_ranges
        fixed_params = {}
        for p in self.param_ranges:
            if not p.get('optimize', True):
                fixed_params[p['name']] = p.get('start', p.get('default', 0))

        # Backtest each of the top 20 passes
        backtest_results = []
        best_result = None
        best_profit = float('-inf')

        self._log(f"Backtesting top {len(top_passes)} passes...")

        for i, pass_data in enumerate(top_passes):
            pass_num = pass_data.get('pass', i + 1)
            params = pass_data.get('params', {})

            # Filter out result fields, keep only input params
            input_params = {k: v for k, v in params.items() if k not in RESULT_FIELDS}

            # Add fixed params (must override to disable broken features)
            input_params.update(fixed_params)

            try:
                result = run_backtest(
                    self.compiled_ea_path,
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    params=input_params,
                    terminal=self.terminal,
                )

                if result.get('success'):
                    result['pass_num'] = pass_num
                    result['input_params'] = input_params
                    result['forward_result'] = params.get('Forward Result', 0)
                    result['back_result'] = params.get('Back Result', 0)
                    backtest_results.append(result)

                    # Track best for Monte Carlo
                    profit = result.get('profit', 0)
                    if profit > best_profit:
                        best_profit = profit
                        best_result = result

            except Exception as e:
                self._log(f"Pass #{pass_num} backtest error: {e}")

        if not backtest_results:
            return False, {'error': 'All backtests failed'}

        # Use best result for overall metrics and Monte Carlo
        self.backtest_results = best_result
        self.top20_backtest_results = backtest_results

        # Update metrics from best result
        metrics = {
            'profit': best_result.get('profit', 0),
            'profit_factor': best_result.get('profit_factor', 0),
            'max_drawdown_pct': best_result.get('max_drawdown_pct', 0),
            'total_trades': best_result.get('total_trades', 0),
            'win_rate': best_result.get('win_rate', 0),
            'sharpe_ratio': best_result.get('sharpe_ratio', 0),
            'sortino_ratio': best_result.get('sortino_ratio', 0),
            'calmar_ratio': best_result.get('calmar_ratio', 0),
            'expected_payoff': best_result.get('expected_payoff', 0),
            'recovery_factor': best_result.get('recovery_factor', 0),
        }
        self.state.update_metrics(metrics)

        # Check gates against best result
        gate_results = gates.check_all_backtest_gates(best_result)
        for name, gate_data in gate_results['gates'].items():
            self.state.update_gates({name: gate_data})

        self._log(f"Backtested {len(backtest_results)}/{len(top_passes)} passes successfully")

        # Save backtest results to disk
        backtest_data = {
            'best_result': best_result,
            'all_results': backtest_results,
        }
        results_file = self._save_results('backtests', backtest_data)
        self._log(f"Backtest results saved to: {results_file}")

        return gate_results['all_passed'], {
            'best_result': best_result,
            'results_file': results_file,
            'successful_count': len(backtest_results),
            'total_count': len(top_passes),
            'gates': gate_results['gates'],
        }

    def _step_monte_carlo(self) -> tuple[bool, dict]:
        """Step 10: Monte Carlo simulation."""
        # Extract trades from backtest results
        trades = extract_trades_from_results(self.backtest_results)

        if not trades:
            return False, {'error': 'No trades to simulate'}

        self.mc_results = run_monte_carlo(trades)

        if not self.mc_results.get('success'):
            return False, self.mc_results

        # Check gates
        gate_results = gates.check_all_monte_carlo_gates(self.mc_results)
        for name, gate_data in gate_results['gates'].items():
            self.state.update_gates({name: gate_data})

        # Update metrics
        self.state.update_metrics({
            'mc_confidence': self.mc_results.get('confidence', 0),
            'mc_ruin_probability': self.mc_results.get('ruin_probability', 100),
        })

        return gate_results['all_passed'], {
            **self.mc_results,
            'gates': gate_results['gates'],
        }

    def _step_generate_reports(self) -> tuple[bool, dict]:
        """Step 11: Generate dashboard and update leaderboard."""
        from reports.workflow_dashboard import generate_dashboard_from_workflow
        from reports.leaderboard import generate_leaderboard

        summary = self.state.get_summary()

        # Calculate composite score
        score = gates.calculate_composite_score(self.state.get('metrics', {}))
        self.state.set('composite_score', score)

        # Check go-live readiness
        go_live = gates.check_go_live_ready(self.state.to_dict())
        self.state.set('go_live', go_live)

        # Generate failure diagnosis if needed
        if not go_live['go_live_ready']:
            diagnoses = gates.diagnose_failure(
                self.state.get('gates', {}),
                self.state.get('metrics', {}),
            )
            self.state.set('diagnoses', diagnoses)

        # Save state before generating reports
        self.state.save()

        # Generate dashboard (fast mode - no backtests, just optimization data)
        dashboard_path = None
        try:
            dashboard_path = generate_dashboard_from_workflow(
                str(self.state.state_file),
                run_backtests=False,  # Fast mode - optimization data only
                open_browser=False,
            )
            self._log(f"Dashboard generated: {dashboard_path}")
        except Exception as e:
            self._log(f"Warning: Dashboard generation failed: {e}")

        # Update leaderboard (adds top 20 passes from this workflow)
        leaderboard_path = None
        try:
            leaderboard_path = generate_leaderboard(open_browser=False)
            self._log(f"Leaderboard updated: {leaderboard_path}")
        except Exception as e:
            self._log(f"Warning: Leaderboard update failed: {e}")

        return True, {
            'summary': summary,
            'composite_score': score,
            'go_live': go_live,
            'state_file': str(self.state.state_file),
            'dashboard_path': dashboard_path,
            'leaderboard_path': leaderboard_path,
        }


def run_workflow(
    ea_path: str,
    terminal_name: Optional[str] = None,
    symbol: str = 'EURUSD',
    timeframe: str = 'H1',
) -> dict:
    """
    Convenience function to run complete workflow.

    Returns workflow summary.
    """
    runner = WorkflowRunner(
        ea_path=ea_path,
        terminal_name=terminal_name,
        symbol=symbol,
        timeframe=timeframe,
        on_progress=print,
    )
    return runner.run()
