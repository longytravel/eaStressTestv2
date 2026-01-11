"""
Workflow Runner

Orchestrates the 11-step EA stress test workflow.
Each step has a gate that must pass before proceeding.
"""
from pathlib import Path
from typing import Optional, Callable
import hashlib
import re
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
    12. Stress Scenarios - spread/latency/tick validation (post-step)
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
        auto_run_stress_scenarios: Optional[bool] = None,
        auto_stats_analysis: Optional[bool] = None,
        auto_run_forward_windows: Optional[bool] = None,
        auto_run_multi_pair: Optional[bool] = None,
        multi_pair_symbols: Optional[list[str]] = None,
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
        self.auto_run_stress_scenarios = auto_run_stress_scenarios
        self.auto_stats_analysis = auto_stats_analysis
        self.auto_run_forward_windows = auto_run_forward_windows
        self.auto_run_multi_pair = auto_run_multi_pair
        self.multi_pair_symbols = multi_pair_symbols
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
        self.stress_results = {}

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

    def _make_report_name(self, tag: str, extra: Optional[str] = None, max_len: int = 60) -> str:
        """
        Generate a deterministic, unique MT5 report name for this workflow.

        MT5 outputs reports into shared terminal folders; without per-workflow naming,
        runs overwrite each other and dashboards become flaky.
        """
        base = f"{self.state.workflow_id}_{tag}"
        if extra:
            base = f"{base}_{extra}"

        safe = re.sub(r"[^A-Za-z0-9_]+", "_", base)
        safe = re.sub(r"_+", "_", safe).strip("_")

        if len(safe) <= max_len:
            return safe

        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
        head = safe[: max_len - 9].rstrip("_")
        return f"{head}_{digest}"

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
        step_1b = steps.get('1b_inject_ontester', {}).get('result') or {}
        if not isinstance(step_1b, dict):
            step_1b = {}
        if step_1b.get('modified_path'):
            self.modified_ea_path = step_1b['modified_path']

        # Restore compiled EA path from step 2
        step_2 = steps.get('2_compile', {}).get('result') or {}
        if not isinstance(step_2, dict):
            step_2 = {}
        if step_2.get('exe_path'):
            self.compiled_ea_path = step_2['exe_path']

        # Restore params from step 3
        step_3 = steps.get('3_extract_params', {}).get('result') or {}
        if not isinstance(step_3, dict):
            step_3 = {}
        if step_3.get('params'):
            self.params = step_3['params']

        # Restore optimization ranges and wide params from step 4 if available
        step_4 = steps.get('4_analyze_params', {}).get('result') or {}
        if not isinstance(step_4, dict):
            step_4 = {}
        if step_4.get('optimization_ranges'):
            self.param_ranges = step_4['optimization_ranges']
        if step_4.get('wide_validation_params'):
            self.wide_validation_params = step_4['wide_validation_params']

        # Restore optimization results from disk (large file)
        step_7 = steps.get('7_run_optimization', {}).get('result') or {}
        if not isinstance(step_7, dict):
            step_7 = {}
        if step_7.get('results_file'):
            self.optimization_results = self._load_results('optimization')
        elif step_7.get('results'):
            # Fallback for legacy runs stored inline
            self.optimization_results = step_7

        # Restore selected passes and analysis from step 8b if available
        step_8b = steps.get('8b_stats_analysis', {}).get('result') or {}
        if not isinstance(step_8b, dict):
            step_8b = {}
        if step_8b.get('selected_passes'):
            self.selected_passes = step_8b['selected_passes']
        if step_8b.get('analysis'):
            self.stats_analysis = step_8b['analysis']

        # Restore backtest results from disk (large file)
        step_9 = steps.get('9_backtest_robust', {}).get('result') or {}
        if not isinstance(step_9, dict):
            step_9 = {}
        if step_9.get('results_file'):
            backtest_data = self._load_results('backtests')
            self.top20_backtest_results = backtest_data.get('all_results', [])
            self.backtest_results = backtest_data.get('best_result', {})

        # Restore previous workflow link if this is an improvement run
        if self.state.get('previous_workflow_id'):
            self.previous_workflow_id = self.state.get('previous_workflow_id')

    def _apply_injected_safety_defaults(
        self,
        wide_validation_params: dict,
        optimization_ranges: list[dict],
    ) -> tuple[dict, list[dict]]:
        """
        Ensure injected safety params are present and NOT optimized.

        - Step 5 validation uses very loose safety to avoid false "no trades".
        - Optimization/backtests use the configured safety defaults.
        """
        wide_validation_params = dict(wide_validation_params or {})
        optimization_ranges = list(optimization_ranges or [])

        safety_defaults = {
            'EAStressSafety_MaxSpreadPips': getattr(settings, 'SAFETY_DEFAULT_MAX_SPREAD_PIPS', 3.0),
            'EAStressSafety_MaxSlippagePips': getattr(settings, 'SAFETY_DEFAULT_MAX_SLIPPAGE_PIPS', 3.0),
        }
        validation_overrides = {
            'EAStressSafety_MaxSpreadPips': getattr(settings, 'SAFETY_VALIDATION_MAX_SPREAD_PIPS', 500.0),
            'EAStressSafety_MaxSlippagePips': getattr(settings, 'SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS', 500.0),
        }

        # Validation (Step 5): loosen safety so we can confirm the EA trades
        for k, v in validation_overrides.items():
            wide_validation_params[k] = v

        # Optimization/backtests: force safety params to fixed defaults (never optimized)
        updated_ranges: list[dict] = []
        found = set()
        for p in optimization_ranges:
            if not isinstance(p, dict):
                continue
            name = p.get('name')
            if name in safety_defaults:
                val = safety_defaults[name]
                updated_ranges.append({
                    **p,
                    'name': name,
                    'start': val,
                    'stop': val,
                    'step': 0,
                    'optimize': False,
                    'default': val,
                    'category': p.get('category', 'safety'),
                    'rationale': p.get('rationale', 'Injected safety parameter (fixed)'),
                })
                found.add(name)
            else:
                updated_ranges.append(p)

        for name, val in safety_defaults.items():
            if name in found:
                continue
            updated_ranges.append({
                'name': name,
                'start': val,
                'stop': val,
                'step': 0,
                'optimize': False,
                'default': val,
                'category': 'safety',
                'rationale': 'Injected safety parameter (fixed)',
            })

        # Carry forward validation-time boolean toggles (e.g., filter disables) when missing.
        # This prevents "0 trades everywhere" optimizations when a critical feature toggle
        # was set in wide_validation_params but omitted from optimization_ranges.
        try:
            known_params = {p.get('name') for p in (self.params or []) if isinstance(p, dict) and p.get('name')}
        except Exception:
            known_params = set()

        existing_names = {p.get('name') for p in updated_ranges if isinstance(p, dict) and p.get('name')}
        for name, value in wide_validation_params.items():
            if name in existing_names:
                continue
            if known_params and name not in known_params:
                continue

            key = str(name or "")
            if not re.match(r"^(Use|Enable)_[A-Za-z0-9_]+$", key):
                continue

            fixed: Optional[int] = None
            if isinstance(value, bool):
                fixed = int(value)
            elif isinstance(value, (int, float)) and float(value) in (0.0, 1.0):
                fixed = int(value)
            if fixed is None:
                continue

            updated_ranges.append({
                'name': key,
                'start': fixed,
                'stop': fixed,
                'step': 0,
                'optimize': False,
                'category': 'toggle',
                'rationale': 'Carried forward from trade-validation params (fixed)',
            })
            existing_names.add(key)

        return wide_validation_params, updated_ranges

    def _step_done(self, step_name: str, passed: bool, result: dict) -> None:
        """Handle step completion."""
        self.state.complete_step(step_name, passed, result)
        if self.on_step_complete:
            self.on_step_complete(step_name, passed, result)

    # =========================================================================
    # STEP VALIDATION & PROTECTION
    # =========================================================================

    def _validate_step_prerequisites(self, required_steps: list[str]) -> tuple[bool, str]:
        """
        Validate that all required steps have passed before proceeding.

        Args:
            required_steps: List of step names that must have passed

        Returns:
            (valid, error_message) - True if all prerequisites met, else False with reason
        """
        steps = self.state.state.get('steps', {})

        for step_name in required_steps:
            step_data = steps.get(step_name, {})
            status = step_data.get('status')

            if status is None:
                return False, f"Prerequisite step '{step_name}' has not been run"
            if status != 'passed':
                return False, f"Prerequisite step '{step_name}' did not pass (status: {status})"

        return True, ""

    def _validate_param_submission(
        self,
        wide_validation_params: dict,
        optimization_ranges: list[dict],
    ) -> list[str]:
        """
        Validate that submitted params are well-formed before accepting them.

        This helps catch cases where /param-analyzer was skipped or produced
        incomplete output.

        Args:
            wide_validation_params: Dict of {param_name: value} for validation
            optimization_ranges: List of param dicts with optimization settings

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # 1. wide_validation_params must be a non-empty dict
        if not isinstance(wide_validation_params, dict):
            errors.append("wide_validation_params must be a dict")
        elif len(wide_validation_params) == 0:
            errors.append("wide_validation_params is empty - did you run /param-analyzer?")

        # 2. optimization_ranges must be a non-empty list
        if not isinstance(optimization_ranges, list):
            errors.append("optimization_ranges must be a list")
        elif len(optimization_ranges) == 0:
            errors.append("optimization_ranges is empty - did you run /param-analyzer?")
        else:
            # 3. Each range must have required keys
            for i, r in enumerate(optimization_ranges):
                if not isinstance(r, dict):
                    errors.append(f"optimization_ranges[{i}] is not a dict")
                    continue

                if 'name' not in r:
                    errors.append(f"optimization_ranges[{i}] missing 'name' key")
                    continue

                name = r['name']
                if 'optimize' not in r:
                    errors.append(f"Parameter '{name}' missing 'optimize' key (True/False)")
                    continue

                # 4. If optimize=True, requires start/step/stop
                if r.get('optimize') is True:
                    for key in ('start', 'step', 'stop'):
                        if key not in r:
                            errors.append(f"Parameter '{name}' has optimize=True but missing '{key}'")

            # 5. Check for unknown param names (typos) if we have extracted params
            if self.params:
                known_names = {p.get('name') for p in self.params if isinstance(p, dict)}
                range_names = {r.get('name') for r in optimization_ranges if isinstance(r, dict)}

                # Check for names in ranges that don't exist in extracted params
                unknown = range_names - known_names
                # Exclude injected safety params from unknown check
                unknown = {n for n in unknown if not n.startswith('EAStressSafety_')}
                if unknown:
                    errors.append(f"Unknown parameter names in optimization_ranges: {unknown}")

                # Check for names in wide_params that don't exist in extracted params
                wide_names = set(wide_validation_params.keys())
                unknown_wide = wide_names - known_names
                # Exclude injected safety params
                unknown_wide = {n for n in unknown_wide if not n.startswith('EAStressSafety_')}
                if unknown_wide:
                    errors.append(f"Unknown parameter names in wide_validation_params: {unknown_wide}")

        return errors

    def _is_step_completed(self, step_name: str) -> bool:
        """Check if a step has already been completed (passed or failed)."""
        steps = self.state.state.get('steps', {})
        step_data = steps.get(step_name, {})
        return step_data.get('status') in ('passed', 'failed')

    def _check_rerun_allowed(self, step_name: str, force: bool = False) -> tuple[bool, str]:
        """
        Check if running a step is allowed (not already completed unless forced).

        Args:
            step_name: Step to check
            force: If True, allow re-running completed steps

        Returns:
            (allowed, warning_message)
        """
        if not self._is_step_completed(step_name):
            return True, ""

        if force:
            return True, f"Re-running already completed step '{step_name}' (forced)"

        return False, f"Step '{step_name}' already completed. Use force=True to re-run."

    # =========================================================================
    # PARAMETER REVIEW FORMATTING
    # =========================================================================

    @staticmethod
    def format_param_review(
        wide_validation_params: dict,
        optimization_ranges: list[dict],
    ) -> dict:
        """
        Format parameters for human review before optimization.

        Returns a dict with:
        - optimizing: list of params being optimized with their ranges
        - fixed: list of params with fixed values
        - toggles: count of boolean toggles
        - continuous: count of continuous params
        - estimated_combinations: rough estimate of total combinations
        - summary_text: formatted text for display
        """
        optimizing = []
        fixed = []
        toggle_count = 0
        continuous_count = 0
        combination_multiplier = 1

        for param in optimization_ranges:
            if not isinstance(param, dict):
                continue

            name = param.get('name', 'unknown')
            optimize = param.get('optimize', False)
            category = param.get('category', '')
            rationale = param.get('rationale', '')

            if optimize:
                if 'start' in param and 'stop' in param:
                    # Continuous parameter
                    start = param.get('start', 0)
                    stop = param.get('stop', 0)
                    step = param.get('step', 1) or 1

                    if step > 0 and stop >= start:
                        num_values = int((stop - start) / step) + 1
                    else:
                        num_values = 1

                    continuous_count += 1
                    combination_multiplier *= num_values

                    optimizing.append({
                        'name': name,
                        'type': 'continuous',
                        'start': start,
                        'step': step,
                        'stop': stop,
                        'values': num_values,
                        'category': category,
                        'rationale': rationale,
                    })
                else:
                    # Boolean toggle
                    toggle_count += 1
                    combination_multiplier *= 2

                    optimizing.append({
                        'name': name,
                        'type': 'toggle',
                        'start': 'false',
                        'step': '-',
                        'stop': 'true',
                        'values': 2,
                        'category': category,
                        'rationale': rationale,
                    })
            else:
                # Fixed parameter
                fixed_value = param.get('fixed_value', param.get('default', param.get('start', 'N/A')))
                fixed.append({
                    'name': name,
                    'value': fixed_value,
                    'category': category,
                    'rationale': rationale,
                })

        # Build summary text
        lines = []
        lines.append("=" * 72)
        lines.append("PARAMETER REVIEW")
        lines.append("=" * 72)
        lines.append("")
        lines.append(f"OPTIMIZING ({len(optimizing)} params):")
        lines.append("-" * 72)
        lines.append(f"{'Name':<30} {'Start':>8} {'Step':>8} {'Stop':>8} {'Values':>6} {'Category':<12}")
        lines.append("-" * 72)

        for p in optimizing:
            start_str = str(p['start']) if p['type'] == 'continuous' else 'bool'
            step_str = str(p['step']) if p['type'] == 'continuous' else '-'
            stop_str = str(p['stop']) if p['type'] == 'continuous' else '-'
            lines.append(f"{p['name']:<30} {start_str:>8} {step_str:>8} {stop_str:>8} {p['values']:>6} {p['category']:<12}")

        lines.append("")
        lines.append(f"FIXED ({len(fixed)} params):")
        lines.append("-" * 72)
        lines.append(f"{'Name':<30} {'Value':<15} {'Reason':<25}")
        lines.append("-" * 72)

        for p in fixed:
            val_str = str(p['value'])[:15]
            reason_str = (p['rationale'] or p['category'])[:25]
            lines.append(f"{p['name']:<30} {val_str:<15} {reason_str:<25}")

        lines.append("")
        lines.append("=" * 72)
        lines.append(f"Toggles: {toggle_count} (2^{toggle_count} = {2**toggle_count:,})")
        lines.append(f"Continuous: {continuous_count}")
        lines.append(f"ESTIMATED COMBINATIONS: {combination_multiplier:,}")
        lines.append("=" * 72)

        return {
            'optimizing': optimizing,
            'fixed': fixed,
            'toggles': toggle_count,
            'continuous': continuous_count,
            'estimated_combinations': combination_multiplier,
            'summary_text': '\n'.join(lines),
        }

    # =========================================================================
    # WORKFLOW EXECUTION
    # =========================================================================

    def run(self, stop_on_failure: bool = True, pause_for_analysis: bool = True, force: bool = False) -> dict:
        """
        Run the complete workflow.

        Args:
            stop_on_failure: If True, stop at first failed gate
            pause_for_analysis: If True, pause after Step 3 for Claude to analyze params
            force: If True, allow re-running even if workflow already started

        Returns:
            Final workflow state summary (or partial if paused)

        Raises:
            RuntimeError: If workflow already in progress/completed and force=False
        """
        # =====================================================================
        # RE-RUN PROTECTION: Check if workflow already started
        # =====================================================================
        current_status = self.state.state.get('status', 'pending')
        if current_status not in ('pending',) and not force:
            raise RuntimeError(
                f"Workflow already has status '{current_status}'. "
                f"Use force=True to restart, or use continue_with_params() to resume."
            )
        if force and current_status != 'pending':
            self._log(f"Re-running workflow (was: {current_status}, forced)")

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
        stop_on_failure: bool = True,
        force: bool = False,
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
            force: If True, allow re-running even if Step 4 already completed

        Returns:
            Final workflow state summary

        Raises:
            ValueError: If prerequisite steps (1-3) have not passed
            RuntimeError: If Step 4 already completed and force=False
        """
        # Restore paths from previous steps if continuing from loaded state
        self._restore_paths_from_state()

        # =====================================================================
        # PREREQUISITE VALIDATION: Steps 1-3 must have passed
        # =====================================================================
        required_steps = [
            '1_load_ea',
            '1b_inject_ontester',
            '1c_inject_safety',
            '2_compile',
            '3_extract_params',
        ]
        valid, error_msg = self._validate_step_prerequisites(required_steps)
        if not valid:
            raise ValueError(f"Cannot continue: {error_msg}")

        # =====================================================================
        # RE-RUN PROTECTION: Check if Step 4 already completed
        # =====================================================================
        allowed, warning = self._check_rerun_allowed('4_analyze_params', force=force)
        if not allowed:
            raise RuntimeError(warning)
        if warning:
            self._log(warning)

        # =====================================================================
        # PARAM VALIDATION: Ensure params are well-formed
        # =====================================================================
        validation_errors = self._validate_param_submission(
            wide_validation_params, optimization_ranges
        )
        if validation_errors:
            error_list = '\n  - '.join(validation_errors)
            raise ValueError(
                f"Invalid parameter submission (did you run /param-analyzer?):\n  - {error_list}"
            )

        # Ensure injected safety params exist and are treated correctly
        wide_validation_params, optimization_ranges = self._apply_injected_safety_defaults(
            wide_validation_params, optimization_ranges
        )

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
        DEPRECATED: Parameter analysis must be done by Claude via /param-analyzer skill.
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

        auto_stats = self.auto_stats_analysis
        if auto_stats is None:
            auto_stats = bool(getattr(settings, 'AUTO_STATS_ANALYSIS', False))

        if auto_stats:
            # ENFORCEMENT: Run reopt_analysis BEFORE auto-selecting passes
            # This ensures the analysis data is captured even in unattended mode
            self._log("AUTO: Running re-optimization analysis before pass selection...")
            try:
                self.run_reopt_analysis()
            except Exception as e:
                self._log(f"Warning: reopt_analysis failed: {e}")

            top_n = int(getattr(settings, 'AUTO_STATS_TOP_N', 20) or 20)
            selected_passes, analysis = self._auto_select_passes(top_n=top_n)
            self._log(f"AUTO: Selected {len(selected_passes)} passes by composite score")
            return self.continue_with_analysis(
                selected_passes, analysis,
                stop_on_failure=stop_on_failure,
                skip_reopt_check=True,  # Already ran above
            )

        # PAUSE for Claude /stats-analyzer to analyze and select top passes
        self.state.set_status('awaiting_stats_analysis')
        self._log("PAUSED: Awaiting Claude stats analysis (call continue_with_analysis)")
        self._log("Invoke /stats-analyzer skill to analyze passes and select top 20")
        return self.state.get_summary()

    def _auto_select_passes(self, top_n: int = 20) -> tuple[list[dict], dict]:
        """
        Deterministically select passes for Step 9 using the leaderboard composite score.

        This enables unattended runs without requiring an LLM for /stats-analyzer.
        """
        results = (self.optimization_results or {}).get('results', []) if isinstance(self.optimization_results, dict) else []

        base_min = int(getattr(settings, 'MIN_TRADES', 50) or 50)
        step8 = (self.state.get('steps', {}) or {}).get('8_parse_results', {})
        step8_res = (step8.get('result') or {}) if isinstance(step8, dict) else {}
        chosen = step8_res.get('min_trades_threshold_used')
        if isinstance(chosen, int) and chosen >= 1:
            thresholds = [chosen]
        else:
            validation_trades = 0
            try:
                step5 = (self.state.get('steps', {}) or {}).get('5_validate_trades', {})
                validation_trades = int(((step5.get('result') or {}).get('metrics') or {}).get('total_trades', 0) or 0)
            except Exception:
                validation_trades = 0

            adaptive = base_min
            if validation_trades > 0:
                adaptive = min(base_min, max(10, int(round(validation_trades * 0.8))))
            thresholds = [adaptive]
            if adaptive > 10:
                thresholds.append(max(10, adaptive // 2))
            thresholds.append(1)
            thresholds = list(dict.fromkeys([t for t in thresholds if isinstance(t, int) and t >= 1]))

        def _build_candidates(min_trades: int) -> list[tuple[float, float, int, dict]]:
            out: list[tuple[float, float, int, dict]] = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                params = r.get('params', {}) if isinstance(r.get('params'), dict) else {}
                pass_num = params.get('Pass')
                if not isinstance(pass_num, int):
                    continue

                trades = int(r.get('total_trades', 0) or 0)
                if trades < int(min_trades or 1):
                    continue

                # Get forward/back results for consistency scoring
                forward = params.get('Forward Result', 0) or 0
                back = params.get('Back Result', 0) or 0

                # Build complete score_metrics with all fields calculate_composite_score expects
                score_metrics = {
                    'profit': r.get('profit', 0),
                    'total_trades': trades,
                    'profit_factor': r.get('profit_factor', 0),
                    'max_drawdown_pct': r.get('max_drawdown_pct', 0),
                    'forward_result': forward,
                    'back_result': back,
                    # Additional metrics
                    'sharpe_ratio': r.get('sharpe_ratio', 0),
                    'recovery_factor': r.get('recovery_factor', 0),
                    'expected_payoff': r.get('expected_payoff', 0),
                }
                score = gates.calculate_composite_score(score_metrics)
                if forward > 0 and back > 0:
                    score = min(10, score + 0.5)

                profit = float(r.get('profit', 0) or 0)
                out.append((float(score), profit, pass_num, params))
            return out

        candidates: list[tuple[float, float, int, dict]] = []
        chosen_threshold = thresholds[-1] if thresholds else 1
        for t in thresholds or [1]:
            candidates = _build_candidates(int(t))
            if candidates:
                chosen_threshold = int(t)
                break

        candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
        chosen = candidates[: max(0, int(top_n or 0))]

        selected_passes = [{'pass': pass_num, 'params': params} for _, _, pass_num, params in chosen]
        analysis = {
            'source': 'auto_score',
            'selection': 'composite_score',
            'top_n': int(top_n or 0),
            'candidate_count': len(candidates),
            'selected_count': len(selected_passes),
            'min_trades_threshold_used': chosen_threshold,
            'min_trades_thresholds_tried': thresholds,
            'note': 'Auto-selected top passes by composite score (+0.5 consistency bonus)',
        }
        return selected_passes, analysis

    def continue_with_analysis(
        self,
        selected_passes: list[dict],
        analysis: dict,
        stop_on_failure: bool = True,
        skip_reopt_check: bool = False,
    ) -> dict:
        """
        Continue workflow from Step 8B with Claude-analyzed passes.

        This should be called after Claude has analyzed optimization results
        with /stats-analyzer and selected the top 20 passes to backtest.

        ENFORCEMENT: Requires run_reopt_analysis() to have been called first,
        unless skip_reopt_check=True (used by auto_stats_analysis after it
        runs the analysis itself).

        Args:
            selected_passes: List of pass dicts selected by Claude (max 20)
            analysis: Claude's analysis dict with reasoning, insights, etc.
            stop_on_failure: If True, stop at first failed gate
            skip_reopt_check: If True, skip enforcement (used by auto mode)

        Returns:
            Final workflow state summary
        """
        # Restore paths from previous steps if continuing from loaded state
        self._restore_paths_from_state()

        # ENFORCEMENT: Require reopt_analysis before proceeding to Step 9
        # This ensures the two-stage optimization process is followed
        if not skip_reopt_check:
            checkpoints = self.state.state.get('checkpoints', {})
            if not checkpoints.get('reopt_analysis_completed'):
                raise ValueError(
                    "Two-stage optimization enforcement: Must call run_reopt_analysis() "
                    "before continue_with_analysis().\n\n"
                    "The two-stage process requires:\n"
                    "1. After Step 8: Call runner.run_reopt_analysis() to analyze results\n"
                    "2. Review analysis: Check toggle patterns and clustering\n"
                    "3. Decision: Either re-optimize with refined ranges, or proceed\n"
                    "4. Then: Call continue_with_analysis() with selected passes\n\n"
                    "To bypass (not recommended): pass skip_reopt_check=True"
                )

        # Store Claude's selections
        self.selected_passes = selected_passes[:20]  # Limit to 20
        self.stats_analysis = analysis

        self.state.set_status('in_progress')

        # Mark Step 8B as passed with Claude's analysis
        self._log("Starting step: 8b_stats_analysis (Claude-analyzed)")
        self.state.start_step('8b_stats_analysis')
        self._step_done('8b_stats_analysis', True, {
            'source': (analysis or {}).get('source', 'claude_analysis') if isinstance(analysis, dict) else 'claude_analysis',
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
        auto_stress = self.auto_run_stress_scenarios
        if auto_stress is None:
            auto_stress = getattr(settings, 'AUTO_RUN_STRESS_SCENARIOS', True)
        if auto_stress:
            phase3b_steps.append(('12_stress_scenarios', self._step_stress_scenarios))

        auto_forward = self.auto_run_forward_windows
        if auto_forward is None:
            auto_forward = bool(getattr(settings, 'AUTO_RUN_FORWARD_WINDOWS', False))
        if auto_forward:
            phase3b_steps.append(('13_forward_windows', self._step_forward_windows))

        auto_multi = self.auto_run_multi_pair
        if auto_multi is None:
            auto_multi = bool(getattr(settings, 'AUTO_RUN_MULTI_PAIR', False))
        if auto_multi:
            phase3b_steps.append(('14_multi_pair', self._step_multi_pair))

        all_passed = True
        should_skip = False  # Track if we should skip to Step 11

        for step_name, step_func in phase3b_steps:
            # Step 11 (generate_reports) ALWAYS runs - users need dashboards
            # Step 12 is post-step and should run even if earlier gates fail.
            post_steps = {'11_generate_reports'}
            if auto_stress:
                post_steps.add('12_stress_scenarios')
            if auto_forward:
                post_steps.add('13_forward_windows')
            if auto_multi:
                post_steps.add('14_multi_pair')

            if should_skip and step_name not in post_steps:
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

        # Final refresh so dashboards/boards reflect any post-steps (stress/forward/multi-pair).
        try:
            from reports.workflow_dashboard import generate_dashboard_from_workflow
            from reports.leaderboard import generate_leaderboard
            from reports.boards import generate_boards

            generate_dashboard_from_workflow(
                str(self.state.state_file),
                run_backtests=False,
                open_browser=False,
            )
            generate_leaderboard(open_browser=False)
            generate_boards(open_browser=False)
        except Exception as e:
            self._log(f"Warning: final report refresh failed: {e}")

        return self.state.get_summary()

    def run_stress_scenarios_only(self, stop_on_failure: bool = False) -> dict:
        """
        Run Step 12 for an existing workflow (useful when AUTO_RUN_STRESS_SCENARIOS=False).

        This will update the workflow state with `stress_scenarios`, regenerate the dashboard,
        and refresh the leaderboard.
        """
        self._restore_paths_from_state()

        previous_status = self.state.get('status')
        self.state.set_status('in_progress')

        self._log("Starting step: 12_stress_scenarios")
        self.state.start_step('12_stress_scenarios')

        try:
            passed, result = self._step_stress_scenarios()
        except Exception as e:
            passed = False
            result = {'error': str(e)}
            self.state.complete_step('12_stress_scenarios', False, result, str(e))

        self._step_done('12_stress_scenarios', passed, result)

        # Restore status unless the stress step failed
        if not passed:
            self.state.set_status('failed')
        else:
            self.state.set_status(previous_status)

        # Keep overall workflow completion flag stable (stress tests are post-step)
        if stop_on_failure and not passed:
            return self.state.get_summary()

        # Refresh reports so the stress results appear in the dashboard/boards.
        try:
            from reports.workflow_dashboard import generate_dashboard_from_workflow
            from reports.leaderboard import generate_leaderboard
            from reports.boards import generate_boards

            generate_dashboard_from_workflow(
                str(self.state.state_file),
                run_backtests=False,
                open_browser=False,
            )
            generate_leaderboard(open_browser=False)
            generate_boards(open_browser=False)
        except Exception as e:
            self._log(f"Warning: report refresh after stress scenarios failed: {e}")

        return self.state.get_summary()

    def run_multi_pair_only(self, stop_on_failure: bool = False) -> dict:
        """
        Run Step 14 for an existing workflow (useful when AUTO_RUN_MULTI_PAIR=False).

        This will update the workflow state with `multi_pair_runs`, regenerate the dashboard,
        and refresh the global boards index.
        """
        self._restore_paths_from_state()

        previous_status = self.state.get('status')
        self.state.set_status('in_progress')

        self._log("Starting step: 14_multi_pair")
        self.state.start_step('14_multi_pair')

        try:
            passed, result = self._step_multi_pair()
        except Exception as e:
            passed = False
            result = {'error': str(e)}
            self.state.complete_step('14_multi_pair', False, result, str(e))

        self._step_done('14_multi_pair', passed, result)

        # Restore status unless the multi-pair step failed
        if not passed:
            self.state.set_status('failed')
        else:
            self.state.set_status(previous_status)

        if stop_on_failure and not passed:
            return self.state.get_summary()

        # Refresh reports so multi-pair links appear in the dashboard/boards.
        try:
            from reports.workflow_dashboard import generate_dashboard_from_workflow
            from reports.boards import generate_boards

            generate_dashboard_from_workflow(
                str(self.state.state_file),
                run_backtests=False,
                open_browser=False,
            )
            generate_boards(open_browser=False)
        except Exception as e:
            self._log(f"Warning: report refresh after multi-pair runs failed: {e}")

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
        runner.auto_run_stress_scenarios = None
        runner.auto_stats_analysis = None
        runner.auto_run_forward_windows = None
        runner.auto_run_multi_pair = None
        runner.multi_pair_symbols = None
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
        runner.stress_results = {}
        runner.previous_workflow_id = None

        # Fix tracking
        runner.fix_attempts = state.get('fix_attempts', 0)
        runner.max_fix_attempts = state.get('max_fix_attempts', 3)
        runner.original_ea_backed_up = state.get('original_ea_backup') is not None
        runner.original_ea_path = state.get('original_ea_backup')

        # Restore all paths from state
        runner._restore_paths_from_state()

        return runner

    def reload_state(self, workflow_id: str = None) -> None:
        """Reload workflow state and restore all paths.

        Use this to reload state into an existing runner instance.
        This is safer than calling state.load() directly.

        Args:
            workflow_id: Optional different workflow to load. If None, reloads current.
        """
        self.state.reload(workflow_id)
        self._restore_paths_from_state()

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
            # Extract from the modified EA so injected safety params are visible to the system
            source_path = self.modified_ea_path or str(self.ea_path)
            self.params = extract_params(str(source_path))
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
        report_name = self._make_report_name('S5_validate', f'{self.symbol}_{self.timeframe}')
        result = run_backtest(
            self.compiled_ea_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            terminal=self.terminal,
            params=self.wide_validation_params if self.wide_validation_params else None,
            report_name=report_name,
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
            report_name = self._make_report_name('S7_opt', f'{self.symbol}_{self.timeframe}')
            ini_path = create_ini_file(
                ea_name=Path(self.compiled_ea_path).name,
                symbol=self.symbol,
                timeframe=self.timeframe,
                param_ranges=self.param_ranges,
                report_name=report_name,
                terminal=self.terminal,
            )
            return True, {'ini_path': ini_path, 'report_name': report_name}
        except Exception as e:
            return False, {'error': str(e)}

    def _step_run_optimization(self) -> tuple[bool, dict]:
        """Step 7: Run optimization."""
        if not self.compiled_ea_path:
            return False, {'error': 'No compiled EA'}

        report_name = self._make_report_name('S7_opt', f'{self.symbol}_{self.timeframe}')
        result = run_optimization(
            self.compiled_ea_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            param_ranges=self.param_ranges,
            report_name=report_name,
            terminal=self.terminal,
            on_progress=self._log,
            progress_interval_s=60,
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
            'report_name': report_name,
            'gate': gate.to_dict(),
        }
        return gate.passed, summary

    def _step_parse_results(self) -> tuple[bool, dict]:
        """Step 8: Parse optimization results (raw data for Claude to analyze)."""
        if not self.optimization_results:
            return False, {'error': 'No optimization results'}

        results = self.optimization_results.get('results', [])

        if not isinstance(results, list) or not results:
            return False, {'error': 'Optimization produced no passes', 'total_passes': 0, 'valid_passes': 0}

        # Determine an adaptive minimum-trades threshold for parsing/selection.
        # Some pairs/timeframes naturally produce fewer trades; failing the whole workflow here makes runs feel flaky.
        base_min = int(getattr(settings, 'MIN_TRADES', 50) or 50)
        validation_trades = 0
        try:
            step5 = (self.state.get('steps', {}) or {}).get('5_validate_trades', {})
            validation_trades = int(((step5.get('result') or {}).get('metrics') or {}).get('total_trades', 0) or 0)
        except Exception:
            validation_trades = 0

        adaptive = base_min
        if validation_trades > 0:
            adaptive = min(base_min, max(10, int(round(validation_trades * 0.8))))

        thresholds = [adaptive]
        if adaptive > 10:
            thresholds.append(max(10, adaptive // 2))
        thresholds.append(1)
        thresholds = list(dict.fromkeys([t for t in thresholds if isinstance(t, int) and t >= 1]))

        trade_counts = [int((r or {}).get('total_trades', 0) or 0) for r in results if isinstance(r, dict)]
        max_trades = max(trade_counts) if trade_counts else 0
        min_trades = min(trade_counts) if trade_counts else 0

        # If literally every pass has 0 trades, this is a real failure (EA/data/symbol issue).
        if max_trades == 0:
            return False, {
                'error': 'Optimization produced 0 trades across all passes (EA/data/symbol issue)',
                'total_passes': len(results),
                'valid_passes': 0,
                'min_trades_thresholds_tried': thresholds,
                'validation_trades': validation_trades,
            }

        valid_by_threshold = {}
        chosen_threshold = thresholds[-1]
        valid_count = 0
        for t in thresholds:
            cnt = sum(1 for r in results if isinstance(r, dict) and int(r.get('total_trades', 0) or 0) >= t)
            valid_by_threshold[str(t)] = cnt
            if cnt > 0:
                chosen_threshold = t
                valid_count = cnt
                break

        # Store results for Claude to analyze
        # NOTE: Full results are stored in optimization_results from Step 7
        # Claude will invoke /stats-analyzer to select top 20

        return True, {
            'total_passes': len(results),
            'valid_passes': valid_count,
            'min_trades_threshold_used': chosen_threshold,
            'min_trades_thresholds_tried': thresholds,
            'valid_passes_by_threshold': valid_by_threshold,
            'validation_trades': validation_trades,
            'min_pass_trades': min_trades,
            'max_pass_trades': max_trades,
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
        best_candidate = (float('-inf'), float('-inf'))
        selection_metric = getattr(settings, 'BEST_PASS_SELECTION', 'score')
        selection_metric = (selection_metric or 'score').strip().lower()

        self._log(f"Backtesting top {len(top_passes)} passes...")

        for i, pass_data in enumerate(top_passes):
            pass_num = pass_data.get('pass', i + 1)
            params = pass_data.get('params', {})
            self._log(f"Backtest {i+1}/{len(top_passes)}: pass #{pass_num}")

            # Filter out result fields, keep only input params
            input_params = {k: v for k, v in params.items() if k not in RESULT_FIELDS}

            # Add fixed params (must override to disable broken features)
            input_params.update(fixed_params)

            try:
                report_name = self._make_report_name('S9_bt', f'pass{pass_num}')
                result = run_backtest(
                    self.compiled_ea_path,
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    params=input_params,
                    report_name=report_name,
                    terminal=self.terminal,
                    on_progress=self._log,
                    progress_interval_s=60,
                )

                if result.get('success'):
                    result['pass_num'] = pass_num
                    result['input_params'] = input_params
                    result['forward_result'] = params.get('Forward Result', 0)
                    result['back_result'] = params.get('Back Result', 0)

                    # Compute leaderboard-aligned composite score for this pass
                    # IMPORTANT: Must include all fields that calculate_composite_score expects:
                    # - profit/total_profit (25% weight)
                    # - total_trades (20% weight)
                    # - forward_result + back_result for consistency (25% weight)
                    # - profit_factor (15% weight)
                    # - max_drawdown (15% weight)
                    score_metrics = {
                        'profit': result.get('profit', 0),
                        'total_trades': result.get('total_trades', 0),
                        'profit_factor': result.get('profit_factor', 0),
                        'max_drawdown_pct': result.get('max_drawdown_pct', 0),
                        'forward_result': params.get('Forward Result', 0),
                        'back_result': params.get('Back Result', 0),
                        # Additional metrics (not used in score but good to have)
                        'sharpe_ratio': result.get('sharpe_ratio', 0),
                        'sortino_ratio': result.get('sortino_ratio', 0),
                        'calmar_ratio': result.get('calmar_ratio', 0),
                        'recovery_factor': result.get('recovery_factor', 0),
                        'expected_payoff': result.get('expected_payoff', 0),
                        'win_rate': result.get('win_rate', 0),
                    }
                    score = gates.calculate_composite_score(score_metrics)

                    # Bonus for positive forward/back optimization results
                    is_consistent = (
                        result.get('forward_result', 0) > 0 and result.get('back_result', 0) > 0
                    )
                    if is_consistent:
                        score = min(10, score + 0.5)

                    result['composite_score'] = score
                    result['is_consistent'] = is_consistent
                    backtest_results.append(result)
                    self._log(
                        f"Backtest {i+1}/{len(top_passes)} OK: "
                        f"profit {result.get('profit', 0):.0f}, "
                        f"PF {result.get('profit_factor', 0):.2f}, "
                        f"DD {result.get('max_drawdown_pct', 0):.1f}%, "
                        f"trades {int(result.get('total_trades', 0) or 0)}"
                    )

                    # Track best for Monte Carlo
                    profit = float(result.get('profit', 0) or 0)
                    candidate = (
                        (profit, score) if selection_metric == 'profit' else (score, profit)
                    )
                    if candidate > best_candidate:
                        best_candidate = candidate
                        best_result = result
                else:
                    errs = result.get('errors', []) if isinstance(result, dict) else []
                    msg = errs[0] if errs else 'Backtest failed'
                    self._log(f"Backtest {i+1}/{len(top_passes)} FAIL: pass #{pass_num} ({msg})")

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
            'max_drawdown': best_result.get('max_drawdown_pct', 0),  # Alias for scoring
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
            'selection': {
                'metric': selection_metric,
                'best_pass_num': best_result.get('pass_num', 0),
                'best_score': best_result.get('composite_score', 0),
            },
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
        pass_num = self.backtest_results.get('pass_num') if isinstance(self.backtest_results, dict) else None

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
            'pass_num': pass_num,
            'gates': gate_results['gates'],
        }

    def _step_generate_reports(self) -> tuple[bool, dict]:
        """Step 11: Generate dashboard and update leaderboard."""
        from reports.workflow_dashboard import generate_dashboard_from_workflow
        from reports.leaderboard import generate_leaderboard
        from reports.boards import generate_boards

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

        # Update global boards (workflow + scenario index)
        boards_path = None
        try:
            boards_path = generate_boards(open_browser=False)
            self._log(f"Boards updated: {boards_path}")
        except Exception as e:
            self._log(f"Warning: Boards update failed: {e}")

        return True, {
            'summary': summary,
            'composite_score': score,
            'go_live': go_live,
            'state_file': str(self.state.state_file),
            'dashboard_path': dashboard_path,
            'leaderboard_path': leaderboard_path,
            'boards_path': boards_path,
        }

    def _step_stress_scenarios(self) -> tuple[bool, dict]:
        """Step 12: Run post-step stress scenarios (spread/latency/tick validation)."""
        from modules.stress_scenarios import run_stress_scenarios

        best = self.backtest_results if isinstance(self.backtest_results, dict) else {}
        pass_num = best.get('pass_num')
        params = best.get('input_params') if isinstance(best.get('input_params'), dict) else None

        if not self.compiled_ea_path or not params:
            self.stress_results = {
                'success': True,
                'skipped': True,
                'reason': 'No best pass available for stress scenarios',
            }
            return True, self.stress_results

        dates = self.state.get('backtest_dates') or settings.get_backtest_dates()

        # Baseline metrics (from Step 9 best pass)
        baseline = {
            'pass_num': pass_num,
            'profit': best.get('profit', 0),
            'profit_factor': best.get('profit_factor', 0),
            'max_drawdown_pct': best.get('max_drawdown_pct', 0),
            'total_trades': best.get('total_trades', 0),
            'history_quality_pct': best.get('history_quality_pct', 0),
            'bars': best.get('bars', 0),
            'ticks': best.get('ticks', 0),
            'symbols': best.get('symbols', 0),
            'report_path': best.get('report_path'),
            'xml_path': best.get('xml_path'),
            'settings': {
                'from_date': dates.get('start'),
                'to_date': dates.get('end'),
                'model': getattr(settings, 'DATA_MODEL', 1),
                'execution_latency_ms': getattr(settings, 'EXECUTION_LATENCY_MS', 0),
                'spread_points': None,
            },
        }

        # Run scenarios (individual scenario failures do not fail the workflow)
        scenario_defs = getattr(settings, 'STRESS_SCENARIOS', None)
        scenarios_override = None
        if isinstance(scenario_defs, list):
            scenarios_override = []
            for s in list(scenario_defs or []):
                if not isinstance(s, dict):
                    continue
                if str(s.get('period') or '').strip().lower() == 'full':
                    overrides = s.get('overrides') if isinstance(s.get('overrides'), dict) else {}
                    scenarios_override.append({
                        **s,
                        'overrides': {
                            **overrides,
                            'from_date': dates.get('start'),
                            'to_date': dates.get('end'),
                        },
                    })
                else:
                    scenarios_override.append(s)

        stress = run_stress_scenarios(
            compiled_ea_path=self.compiled_ea_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            params=params,
            terminal=self.terminal,
            scenarios=scenarios_override,
            workflow_dates=dates,
            baseline=baseline,
            on_progress=self._log,
        )

        # Attach gate checks + scores per scenario for reporting
        scenarios = stress.get('scenarios', []) if isinstance(stress, dict) else []
        for s in scenarios:
            r = s.get('result', {}) if isinstance(s, dict) else {}
            pf = r.get('profit_factor', 0)
            dd = r.get('max_drawdown_pct', 0)
            trades = r.get('total_trades', 0)

            s['gates'] = {
                'profit_factor': gates.check_profit_factor(pf).to_dict(),
                'max_drawdown': gates.check_max_drawdown(dd).to_dict(),
                'minimum_trades': gates.check_minimum_trades(int(trades or 0)).to_dict(),
            }
            s['score'] = gates.calculate_composite_score({
                'profit_factor': pf,
                'max_drawdown': dd,
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
                'calmar_ratio': 0,
                'recovery_factor': 0,
                'expected_payoff': 0,
                'win_rate': 0,
                'param_stability': 0.5,
            })

        self.stress_results = {
            'success': True,
            'pass_num': pass_num,
            'baseline': baseline,
            **(stress if isinstance(stress, dict) else {}),
        }

        # Persist at top-level so report generation can pick it up immediately
        # (step completion happens after this method returns).
        self.state.set('stress_scenarios', self.stress_results)

        # Regenerate reports so dashboards/leaderboard can display stress results
        dashboard_path = None
        leaderboard_path = None
        boards_path = None
        try:
            from reports.workflow_dashboard import generate_dashboard_from_workflow
            dashboard_path = generate_dashboard_from_workflow(
                str(self.state.state_file),
                run_backtests=False,
                open_browser=False,
            )
        except Exception as e:
            self._log(f"Warning: Stress dashboard regeneration failed: {e}")

        try:
            from reports.leaderboard import generate_leaderboard
            leaderboard_path = generate_leaderboard(open_browser=False)
        except Exception as e:
            self._log(f"Warning: Stress leaderboard regeneration failed: {e}")

        try:
            from reports.boards import generate_boards
            boards_path = generate_boards(open_browser=False)
        except Exception as e:
            self._log(f"Warning: Stress boards regeneration failed: {e}")

        return True, {
            **self.stress_results,
            'dashboard_path': dashboard_path,
            'leaderboard_path': leaderboard_path,
            'boards_path': boards_path,
        }

    def _step_forward_windows(self) -> tuple[bool, dict]:
        """Step 13: Compute forward window slices from the best-pass trade list."""
        from datetime import datetime, timedelta, date
        from modules.trade_extractor import extract_trades

        best = self.backtest_results if isinstance(self.backtest_results, dict) else {}
        report_path = best.get('report_path')
        pass_num = best.get('pass_num')

        if not report_path:
            result = {
                'success': True,
                'skipped': True,
                'reason': 'No best-pass report available for forward windows',
            }
            self.state.set('forward_windows', result)
            return True, result

        dates = self.state.get('backtest_dates') or settings.get_backtest_dates()

        def _parse(value: str) -> Optional[datetime]:
            try:
                return datetime.strptime(str(value), "%Y.%m.%d")
            except Exception:
                return None

        start_dt = _parse(dates.get('start'))
        end_dt = _parse(dates.get('end')) or datetime.now()
        split_dt = _parse(dates.get('split'))

        trades_res = extract_trades(str(report_path))
        if not trades_res.success or not trades_res.trades:
            result = {
                'success': False,
                'pass_num': pass_num,
                'report_path': str(report_path),
                'error': trades_res.error or 'Failed to extract trades for forward windows',
            }
            self.state.set('forward_windows', result)
            return True, result

        trades_sorted = sorted(trades_res.trades, key=lambda t: t.close_time)

        def _metrics_for_window(window_start: datetime, window_end: datetime) -> dict:
            # Start from the balance at window_start to get realistic drawdown %
            balance = float(trades_res.initial_balance or getattr(settings, 'DEPOSIT', 0) or 0)
            for t in trades_sorted:
                if t.close_time < window_start:
                    balance += float(t.net_profit or 0)
                else:
                    break

            start_balance = balance
            peak = start_balance if start_balance != 0 else max(start_balance, 1e-9)
            max_dd = 0.0

            profit = 0.0
            gross_profit = 0.0
            gross_loss = 0.0
            wins = 0
            total = 0

            for t in trades_sorted:
                if t.close_time < window_start:
                    continue
                if t.close_time > window_end:
                    break

                p = float(t.net_profit or 0)
                total += 1
                profit += p
                if p > 0:
                    wins += 1
                    gross_profit += p
                elif p < 0:
                    gross_loss += abs(p)

                balance += p
                if balance > peak:
                    peak = balance
                if peak > 0:
                    dd = (peak - balance) / peak
                    if dd > max_dd:
                        max_dd = dd

            pf = 0.0
            if gross_loss <= 1e-12:
                pf = 99.0 if gross_profit > 0 else 0.0
            else:
                pf = gross_profit / gross_loss

            win_rate = (wins / total * 100.0) if total > 0 else 0.0

            return {
                'profit': float(profit),
                'profit_factor': float(pf),
                'max_drawdown_pct': float(max_dd * 100.0),
                'total_trades': int(total),
                'win_rate': float(win_rate),
            }

        windows: list[dict] = []

        def _add_window(window_id: str, label: str, ws: datetime, we: datetime, kind: str = 'window') -> None:
            if ws > we:
                return
            windows.append({
                'id': window_id,
                'label': label,
                'kind': kind,
                'from_date': ws.strftime("%Y.%m.%d"),
                'to_date': we.strftime("%Y.%m.%d"),
                'metrics': _metrics_for_window(ws, we),
            })

        # Full / In-sample / Forward
        if start_dt:
            _add_window('full', 'Full period', start_dt, end_dt, kind='full')
        if start_dt and split_dt:
            _add_window('in_sample', 'In-sample', start_dt, split_dt, kind='segment')
        if split_dt:
            _add_window('forward', 'Forward', split_dt, end_dt, kind='segment')

        # Rolling windows (relative to the workflow end date)
        for days in list(getattr(settings, 'STRESS_WINDOW_ROLLING_DAYS', []) or []):
            try:
                d = int(days)
            except Exception:
                continue
            if d <= 0:
                continue
            ws = end_dt - timedelta(days=d)
            _add_window(f'last_{d}d', f'Last {d} days', ws, end_dt, kind='rolling')

        # Calendar month windows (relative to the workflow end date)
        for months_ago in list(getattr(settings, 'STRESS_WINDOW_CALENDAR_MONTHS_AGO', []) or []):
            try:
                m = int(months_ago)
            except Exception:
                continue
            if m <= 0:
                continue
            anchor_month_start = date(end_dt.year, end_dt.month, 1)
            year = anchor_month_start.year
            month = anchor_month_start.month - m
            while month <= 0:
                year -= 1
                month += 12
            month_start = date(year, month, 1)
            next_year = year + (1 if month == 12 else 0)
            next_month = 1 if month == 12 else month + 1
            month_end = date(next_year, next_month, 1) - timedelta(days=1)
            ws = datetime.combine(month_start, datetime.min.time())
            we = datetime.combine(month_end, datetime.min.time())
            _add_window(f'month_{month_start.year}_{month_start.month:02d}', month_start.strftime('%b %Y'), ws, we, kind='calendar')

        # Yearly slices (clamped to backtest range)
        if start_dt:
            for year in range(start_dt.year, end_dt.year + 1):
                ws = datetime(year, 1, 1)
                we = datetime(year, 12, 31)
                if ws < start_dt:
                    ws = start_dt
                if we > end_dt:
                    we = end_dt
                _add_window(f'year_{year}', f'Year {year}', ws, we, kind='year')

        result = {
            'success': True,
            'pass_num': pass_num,
            'report_path': str(report_path),
            'history_quality_pct': best.get('history_quality_pct', 0),
            'model': best.get('model', getattr(settings, 'DATA_MODEL', 1)),
            'window_count': len(windows),
            'windows': windows,
        }

        self.state.set('forward_windows', result)

        # Refresh dashboard + boards so users can see the windows immediately
        dashboard_path = None
        boards_path = None
        try:
            from reports.workflow_dashboard import generate_dashboard_from_workflow
            dashboard_path = generate_dashboard_from_workflow(
                str(self.state.state_file),
                run_backtests=False,
                open_browser=False,
            )
        except Exception as e:
            self._log(f"Warning: Forward windows dashboard regeneration failed: {e}")

        try:
            from reports.boards import generate_boards
            boards_path = generate_boards(open_browser=False)
        except Exception as e:
            self._log(f"Warning: Forward windows boards regeneration failed: {e}")

        return True, {**result, 'dashboard_path': dashboard_path, 'boards_path': boards_path}

    def _step_multi_pair(self) -> tuple[bool, dict]:
        """Step 14: Run the workflow on additional symbols (optimized per symbol)."""
        symbols = self.multi_pair_symbols
        if symbols is None:
            symbols = list(getattr(settings, 'MULTI_PAIR_SYMBOLS', []) or [])
        symbols = [str(s).strip().upper() for s in (symbols or []) if str(s).strip()]

        symbols = [s for s in symbols if s and s != str(self.symbol or '').strip().upper()]
        symbols = list(dict.fromkeys(symbols))  # stable unique

        if not symbols:
            result = {'success': True, 'skipped': True, 'reason': 'No additional symbols configured'}
            self.state.set('multi_pair_runs', result)
            return True, result

        if not self.wide_validation_params or not self.param_ranges:
            result = {'success': True, 'skipped': True, 'reason': 'No stored params/ranges available for multi-pair'}
            self.state.set('multi_pair_runs', result)
            return True, result

        runs: list[dict] = []

        for sym in symbols:
            try:
                self._log(f"Multi-pair: starting {sym} {self.timeframe}")
                child = WorkflowRunner(
                    ea_path=str(self.ea_path),
                    terminal_name=self.terminal.get('name'),
                    symbol=sym,
                    timeframe=self.timeframe,
                    auto_run_stress_scenarios=True,
                    auto_stats_analysis=True,
                    auto_run_forward_windows=True,
                    auto_run_multi_pair=False,  # prevent recursion
                    on_progress=self.on_progress,
                )

                # Phase 1 (Steps 1-3) then continue with reused params/ranges
                child.run(stop_on_failure=False, pause_for_analysis=True)
                summary = child.continue_with_params(
                    wide_validation_params=self.wide_validation_params,
                    optimization_ranges=self.param_ranges,
                    stop_on_failure=False,
                )

                runs.append({
                    'symbol': sym,
                    'workflow_id': summary.get('workflow_id'),
                    'status': summary.get('status'),
                    'dashboard_path': summary.get('dashboard_path'),
                    'leaderboard_path': summary.get('leaderboard_path'),
                    'boards_path': summary.get('boards_path'),
                    'composite_score': summary.get('composite_score'),
                    'go_live': summary.get('go_live'),
                })
            except Exception as e:
                runs.append({
                    'symbol': sym,
                    'success': False,
                    'error': str(e),
                })

        result = {
            'success': True,
            'symbol_count': len(symbols),
            'symbols': symbols,
            'runs': runs,
        }

        self.state.set('multi_pair_runs', result)

        # Refresh boards so the new workflows are visible in the global index
        boards_path = None
        try:
            from reports.boards import generate_boards
            boards_path = generate_boards(open_browser=False)
        except Exception as e:
            self._log(f"Warning: Multi-pair boards regeneration failed: {e}")

        return True, {**result, 'boards_path': boards_path}

    # =========================================================================
    # RE-OPTIMIZATION METHODS
    # =========================================================================

    def run_reopt_analysis(self) -> dict:
        """
        Run re-optimization analysis after Step 8.

        MUST be called before continue_with_refined_ranges().
        Analyzes all optimization passes to identify parameter patterns.

        Returns:
            ReoptAnalysis dict with toggle stats, clustering data, and recommendation

        Raises:
            ValueError: If Steps 1-8 not completed
        """
        from modules.reopt_analyzer import analyze_for_reoptimization, format_analysis_report

        # Validate prerequisites
        if self.state.state.get('current_step', 0) < 8:
            raise ValueError(
                "Cannot run re-optimization analysis: Steps 1-8 must be completed first"
            )

        # Get optimization results
        step8_result = self.state.get_step_result('8_parse_results') or {}
        all_passes = step8_result.get('valid_passes', [])

        # Also try to get from optimization_results
        if not all_passes and self.optimization_results:
            all_passes = self.optimization_results.get('valid_passes', [])

        # Get top passes
        step8b_result = self.state.get_step_result('8b_stats_analysis') or {}
        top_passes = step8b_result.get('selected_passes', self.selected_passes or [])

        # Get original ranges
        original_ranges = self.param_ranges or self.state.state.get('optimization_ranges', [])

        self._log("Running re-optimization analysis...")

        # Run analysis
        analysis = analyze_for_reoptimization(
            all_passes=all_passes,
            top_passes=top_passes,
            original_ranges=original_ranges,
            top_n=20,
        )

        # Store in state
        self.state.state['reopt_analysis'] = analysis.to_dict()
        self.state.state['checkpoints']['reopt_analysis_completed'] = True
        self.state.save()

        # Log results
        self._log(f"Re-optimization analysis complete:")
        self._log(f"  Total passes: {analysis.total_passes}")
        self._log(f"  Valid passes: {analysis.valid_passes}")
        self._log(f"  Should re-optimize: {analysis.recommendation.should_reoptimize}")
        self._log(f"  Confidence: {analysis.recommendation.confidence}")

        # Print formatted report
        report = format_analysis_report(analysis)
        self._log(report)

        return analysis.to_dict()

    def continue_with_refined_ranges(
        self,
        refined_ranges: list[dict],
        notes: str = "",
        stop_on_failure: bool = True,
    ) -> dict:
        """
        Re-run optimization with refined parameter ranges.

        Jumps to Step 6 (Create INI) and continues through Step 8.
        After this, run_reopt_analysis() must be called again before
        continuing to Step 9.

        HARD ENFORCEMENT:
        - Raises if re_optimization_count >= REOPT_MAX_ITERATIONS
        - Raises if reopt_analysis not completed
        - Raises if Steps 1-8 not done

        Args:
            refined_ranges: New optimization ranges (same format as original)
            notes: Optional notes about why ranges were refined
            stop_on_failure: If True, stop at first failed gate

        Returns:
            Workflow state summary after re-optimization
        """
        # Hard enforcement: Max iterations
        max_iterations = getattr(settings, 'REOPT_MAX_ITERATIONS', 2)
        current_count = self.state.state.get('re_optimization_count', 0)

        if current_count >= max_iterations:
            raise ValueError(
                f"Maximum re-optimization iterations ({max_iterations}) reached. "
                f"Cannot re-optimize further."
            )

        # Hard enforcement: Analysis must be completed
        checkpoints = self.state.state.get('checkpoints', {})
        if not checkpoints.get('reopt_analysis_completed'):
            raise ValueError(
                "Must call run_reopt_analysis() before continue_with_refined_ranges(). "
                "Cannot skip the analysis step."
            )

        # Hard enforcement: Steps 1-8 must be done
        if self.state.state.get('current_step', 0) < 8:
            raise ValueError(
                "Steps 1-8 must be completed before re-optimization."
            )

        # Restore paths from state
        self._restore_paths_from_state()

        self._log(f"Starting re-optimization (iteration {current_count + 1}/{max_iterations})...")
        if notes:
            self._log(f"Notes: {notes}")

        # Store previous ranges for comparison
        self.state.state['previous_optimization_ranges'] = self.param_ranges.copy() if self.param_ranges else None

        # Update ranges
        self.param_ranges = refined_ranges
        self.state.state['optimization_ranges'] = refined_ranges

        # Increment counter
        self.state.state['re_optimization_count'] = current_count + 1

        # Reset checkpoints for new optimization
        self.state.state['checkpoints']['reopt_analysis_completed'] = False
        self.state.state['checkpoints']['reopt_decision_made'] = True

        # Clear previous optimization results
        self.optimization_results = None
        self.selected_passes = []

        self.state.set_status('in_progress')
        self.state.save()

        # Run Steps 6-8
        return self._run_reopt_steps(stop_on_failure)

    def _run_reopt_steps(self, stop_on_failure: bool = True) -> dict:
        """Run Steps 6-8 for re-optimization."""
        reopt_steps = [
            ('6_create_ini', self._step_create_ini),
            ('7_run_optimization', self._step_run_optimization),
            ('8_parse_results', self._step_parse_results),
        ]

        all_passed = True

        for step_name, step_func in reopt_steps:
            self._log(f"Starting step: {step_name} (re-optimization)")
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
                if stop_on_failure:
                    break
            else:
                self._log(f"Step {step_name} PASSED")

        # Update status
        if all_passed:
            self.state.set_status('awaiting_stats_analysis')
            self._log("Re-optimization complete. Run run_reopt_analysis() to analyze results.")
        else:
            self.state.set_status('failed')

        return self.state.get_summary()

    def get_reopt_status(self) -> dict:
        """Get current re-optimization status."""
        return {
            're_optimization_count': self.state.state.get('re_optimization_count', 0),
            'max_iterations': getattr(settings, 'REOPT_MAX_ITERATIONS', 2),
            'analysis_completed': self.state.state.get('checkpoints', {}).get('reopt_analysis_completed', False),
            'decision_made': self.state.state.get('checkpoints', {}).get('reopt_decision_made', False),
            'previous_ranges': self.state.state.get('previous_optimization_ranges'),
            'reopt_analysis': self.state.state.get('reopt_analysis'),
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
