"""
Stage 6: Create INI File

Converts optimization_ranges to MT5 INI format for optimization.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class CreateINIStage:
    """Stage 6: Generate MT5 optimization INI file from ranges."""

    @property
    def name(self) -> str:
        return "6_create_ini"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Generate INI file for MT5 optimization.

        Requires:
            - Step 2 (compile) completed with exe_path
            - Step 4 (analyze_params) completed with optimization_ranges

        Args:
            state: Current workflow state
            mt5: MT5 interface (not required for INI generation)

        Returns:
            StageResult with ini_path and parameter counts
        """
        import settings

        # Get compiled EA path from Step 2
        step_2 = state.steps.get("2_compile")
        if not step_2 or not step_2.passed or not step_2.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 2 (compile) must complete successfully first",),
            )
        exe_path = step_2.result.get("exe_path")
        if not exe_path:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No compiled EA path from Step 2",),
            )

        # Get optimization_ranges from Step 4
        step_4 = state.steps.get("4_analyze_params")
        if not step_4 or not step_4.passed or not step_4.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 4 (analyze params) must complete successfully first",),
            )
        optimization_ranges = step_4.result.get("optimization_ranges")
        if not optimization_ranges:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No optimization_ranges from Step 4",),
            )

        # Get EA name from compiled path
        ea_name = Path(exe_path).name
        ea_stem = Path(exe_path).stem

        # Build INI content
        dates = settings.get_backtest_dates()
        tf_value = self._timeframe_to_minutes(state.timeframe)

        # Deterministic report name
        report_name = f"{ea_stem}_S6_opt_{state.symbol}_{state.timeframe}_{state.workflow_id[:8]}"

        ini_lines = [
            "; EA Stress Test - Optimization Configuration",
            f"; Generated: {datetime.now().isoformat()}",
            "",
            "[Tester]",
            f"Expert={ea_name}",
            f"Symbol={state.symbol}",
            f"Period={tf_value}",
            f'FromDate={dates["start"]}',
            f'ToDate={dates["end"]}',
            f"ForwardMode={getattr(settings, 'FORWARD_MODE', 2)}",
            f'ForwardDate={dates["split"]}',
            f"Model={getattr(settings, 'DATA_MODEL', 1)}",
            f"ExecutionMode={getattr(settings, 'EXECUTION_LATENCY_MS', 10)}",
            "Optimization=2",  # Genetic algorithm
            f"OptimizationCriterion={getattr(settings, 'OPTIMIZATION_CRITERION', 6)}",
            f"Report={report_name}",
            "ReplaceReport=1",
            "UseLocal=1",
            "Visual=0",
            "ShutdownTerminal=1",
            f"Deposit={getattr(settings, 'DEPOSIT', 3000)}",
            f"Currency={getattr(settings, 'CURRENCY', 'GBP')}",
            f"Leverage={getattr(settings, 'LEVERAGE', 100)}",
        ]

        # Add parameter ranges
        ini_lines.append("")
        ini_lines.append("[TesterInputs]")

        optimizing_count = 0
        for param in optimization_ranges:
            name = param.get("name")
            if not name:
                continue

            line = self._format_param_line(param)
            ini_lines.append(line)

            # Count optimizing params
            if line.endswith("||Y"):
                optimizing_count += 1

        ini_content = "\n".join(ini_lines)

        # Write INI file to workflow directory
        if state.workflow_dir:
            ini_path = Path(state.workflow_dir) / f"{report_name}.ini"
        else:
            ini_path = Path(f"{report_name}.ini")

        ini_path.parent.mkdir(parents=True, exist_ok=True)
        ini_path.write_text(ini_content, encoding="utf-8")

        return StageResult(
            success=True,
            data={
                "ini_path": str(ini_path),
                "report_name": report_name,
                "param_count": len(optimization_ranges),
                "optimizing_count": optimizing_count,
            },
            gate=None,
            errors=(),
        )

    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """Convert timeframe string to MT5 period value."""
        tf_map = {
            "M1": 1,
            "M5": 5,
            "M15": 15,
            "M30": 30,
            "H1": 60,
            "H4": 240,
            "D1": 1440,
            "W1": 10080,
            "MN1": 43200,
        }
        return tf_map.get(timeframe.upper(), 60)

    def _format_param_line(self, param: dict) -> str:
        """Format a parameter for INI file.

        Format: {name}={value}||{start}||{step}||{stop}||{Y/N}
        """
        name = param["name"]

        # Handle fixed boolean parameters
        if "fixed" in param and isinstance(param["fixed"], bool):
            val = "true" if param["fixed"] else "false"
            return f"{name}={val}||{val}||0||{val}||N"

        # Get range values
        start = param.get("start", param.get("fixed_value", param.get("default", 0)))
        step = param.get("step", 1)
        stop = param.get("stop", start)
        optimize = param.get("optimize", True)

        # Detect boolean toggles by name pattern
        is_boolean_toggle = (
            name.startswith(("Enable_", "Use_", "Avoid_", "Allow_", "Is_", "Has_"))
            and optimize
            and "stop" not in param
        )
        if is_boolean_toggle:
            start = 0
            step = 1
            stop = 1

        # Format line
        if optimize and step > 0:
            return f"{name}={start}||{start}||{step}||{stop}||Y"
        else:
            return f"{name}={start}||{start}||0||{start}||N"
