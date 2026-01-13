"""
Stage 12: Stress Scenarios

Run stress tests on the best pass to verify robustness under different
execution conditions (windows, models, latency, cost overlays).
"""

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class StressScenariosStage:
    """Stage 12: Run multi-window stress tests on best pass."""

    @property
    def name(self) -> str:
        return "12_stress_scenarios"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Execute stress scenario suite.

        Requires:
            - Step 9 (backtest_passes) completed with best pass
            - MT5 interface for running backtests

        Generates scenarios dynamically:
            - Rolling windows (7/14/30/60/90 days)
            - Calendar months (1/2/3 months ago)
            - Model variants (OHLC, Tick)
            - Tick latency variants
            - Cost overlays (spread/slippage)

        Args:
            state: Current workflow state
            mt5: MT5 interface (required for base scenarios)

        Returns:
            StageResult with scenario results (informational, no gate)
        """
        import settings

        # Get best pass from Step 9
        step_9 = state.steps.get("9_backtest_passes")
        if not step_9 or not step_9.passed or not step_9.result:
            return StageResult(
                success=True,
                data={"skipped": True, "reason": "No best-pass results from Step 9"},
                gate=None,
                errors=(),
            )

        best_pass = step_9.result.get("best_pass")
        if not best_pass:
            return StageResult(
                success=True,
                data={"skipped": True, "reason": "No best pass selected in Step 9"},
                gate=None,
                errors=(),
            )

        # Get compiled EA path from Step 2
        step_2 = state.steps.get("2_compile")
        if not step_2 or not step_2.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No compiled EA from Step 2",),
            )
        exe_path = step_2.result.get("exe_path")

        # Get params from best pass
        input_params = best_pass.get("input_params", {})
        pass_num = best_pass.get("pass_num", 0)
        baseline_report = best_pass.get("report_path")

        # Build baseline info
        baseline = {
            "pass_num": pass_num,
            "profit": best_pass.get("profit", 0),
            "profit_factor": best_pass.get("profit_factor", 0),
            "max_drawdown_pct": best_pass.get("max_drawdown_pct", 0),
            "total_trades": best_pass.get("total_trades", 0),
            "report_path": baseline_report,
            "settings": {
                "from_date": state.start_date,
                "to_date": state.end_date,
                "model": 1,
                "execution_latency_ms": 10,
            },
        }

        # Build dynamic scenario suite
        scenarios = self._build_scenarios(state, settings)

        # If no MT5 interface, skip execution but return scenario plan
        if mt5 is None:
            return StageResult(
                success=True,
                data={
                    "pass_num": pass_num,
                    "scenario_count": len(scenarios),
                    "baseline": baseline,
                    "scenarios": scenarios,
                    "skipped": True,
                    "reason": "No MT5 interface for scenario execution",
                },
                gate=None,
                errors=(),
            )

        # Execute each base scenario
        executed_scenarios = []
        for scenario in scenarios:
            if scenario.get("variant") == "overlay":
                # Overlays computed post-hoc, not executed
                executed_scenarios.append(scenario)
                continue

            result = self._run_scenario(
                mt5=mt5,
                exe_path=Path(exe_path),
                state=state,
                params=input_params,
                scenario=scenario,
                settings=settings,
            )
            executed_scenarios.append(result)

        # Compute overlay scenarios from base results
        if getattr(settings, "STRESS_INCLUDE_OVERLAYS", True):
            executed_scenarios = self._compute_overlays(
                executed_scenarios, settings
            )

        return StageResult(
            success=True,
            data={
                "pass_num": pass_num,
                "scenario_count": len(executed_scenarios),
                "baseline": baseline,
                "scenarios": executed_scenarios,
            },
            gate=None,
            errors=(),
        )

    def _build_scenarios(
        self, state: "WorkflowState", settings: Any
    ) -> list[dict[str, Any]]:
        """Build dynamic scenario suite based on settings."""
        scenarios = []

        # Parse end date
        try:
            end_date = datetime.strptime(state.end_date, "%Y.%m.%d")
        except (ValueError, TypeError):
            end_date = datetime.now()

        # Rolling windows
        rolling_days = getattr(settings, "STRESS_WINDOW_ROLLING_DAYS", [7, 14, 30, 60, 90])
        models = getattr(settings, "STRESS_WINDOW_MODELS", [1, 0])
        tick_latencies = getattr(settings, "STRESS_TICK_LATENCY_MS", [250, 5000])

        for days in rolling_days:
            window_start = end_date - timedelta(days=days)
            window_id = f"last_{days}d"
            window_label = f"Last {days} days"

            for model in models:
                model_name = "ohlc" if model == 1 else "tick"
                scenario_id = f"{model_name}_{window_id}"

                scenarios.append({
                    "id": scenario_id,
                    "label": f"{model_name.upper()} - {window_label}",
                    "period": window_id,
                    "window": {
                        "id": window_id,
                        "label": window_label,
                        "from_date": window_start.strftime("%Y.%m.%d"),
                        "to_date": end_date.strftime("%Y.%m.%d"),
                    },
                    "tags": ["window", model_name],
                    "variant": "base",
                    "settings": {
                        "from_date": window_start.strftime("%Y.%m.%d"),
                        "to_date": end_date.strftime("%Y.%m.%d"),
                        "model": model,
                        "execution_latency_ms": 10,
                        "spread_points": None,
                    },
                })

                # Tick-only latency variants
                if model == 0:
                    for latency in tick_latencies:
                        lat_id = f"{scenario_id}_latency_{latency}ms"
                        scenarios.append({
                            "id": lat_id,
                            "label": f"Tick {window_label} (latency {latency}ms)",
                            "period": window_id,
                            "window": {
                                "id": window_id,
                                "label": window_label,
                                "from_date": window_start.strftime("%Y.%m.%d"),
                                "to_date": end_date.strftime("%Y.%m.%d"),
                            },
                            "tags": ["window", "tick", "latency"],
                            "variant": "base",
                            "settings": {
                                "from_date": window_start.strftime("%Y.%m.%d"),
                                "to_date": end_date.strftime("%Y.%m.%d"),
                                "model": 0,
                                "execution_latency_ms": latency,
                                "spread_points": None,
                            },
                        })

        # Calendar months
        calendar_months = getattr(settings, "STRESS_WINDOW_CALENDAR_MONTHS_AGO", [1, 2, 3])
        for months_ago in calendar_months:
            # Calculate month boundaries
            month_date = end_date.replace(day=1)
            for _ in range(months_ago):
                month_date = (month_date - timedelta(days=1)).replace(day=1)

            # Last day of month
            if month_date.month == 12:
                next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
            else:
                next_month = month_date.replace(month=month_date.month + 1, day=1)
            month_end = next_month - timedelta(days=1)

            window_id = f"month_{month_date.year}_{month_date.month:02d}"
            window_label = month_date.strftime("%b %Y")

            for model in models:
                model_name = "ohlc" if model == 1 else "tick"
                scenario_id = f"{model_name}_{window_id}"

                scenarios.append({
                    "id": scenario_id,
                    "label": f"{model_name.upper()} - {window_label}",
                    "period": window_id,
                    "window": {
                        "id": window_id,
                        "label": window_label,
                        "from_date": month_date.strftime("%Y.%m.%d"),
                        "to_date": month_end.strftime("%Y.%m.%d"),
                    },
                    "tags": ["calendar", model_name],
                    "variant": "base",
                    "settings": {
                        "from_date": month_date.strftime("%Y.%m.%d"),
                        "to_date": month_end.strftime("%Y.%m.%d"),
                        "model": model,
                        "execution_latency_ms": 10,
                        "spread_points": None,
                    },
                })

        return scenarios

    def _run_scenario(
        self,
        mt5: "MT5Interface",
        exe_path: Path,
        state: "WorkflowState",
        params: dict[str, Any],
        scenario: dict[str, Any],
        settings: Any,
    ) -> dict[str, Any]:
        """Run a single stress scenario backtest."""
        scenario_settings = scenario["settings"]

        # Generate deterministic report name
        ea_stem = exe_path.stem
        scenario_id = scenario["id"]
        hash_input = f"{ea_stem}:{scenario_id}"
        hash8 = hashlib.sha1(hash_input.encode()).hexdigest()[:8]
        report_name = f"{ea_stem}_S12_{scenario_id}_{hash8}"

        try:
            result = mt5.backtest(
                ea_path=exe_path,
                symbol=state.symbol,
                timeframe=state.timeframe,
                params=params,
                from_date=scenario_settings.get("from_date"),
                to_date=scenario_settings.get("to_date"),
                model=scenario_settings.get("model", 1),
                execution_latency_ms=scenario_settings.get("execution_latency_ms", 10),
                report_name=report_name,
            )

            # Build scenario result
            scenario_result = dict(scenario)
            scenario_result["report_name"] = report_name
            scenario_result["success"] = True
            scenario_result["result"] = {
                "profit": result.profit,
                "profit_factor": result.profit_factor,
                "max_drawdown_pct": result.max_drawdown_pct,
                "total_trades": result.total_trades,
                "history_quality_pct": getattr(result, "history_quality_pct", None),
                "bars": getattr(result, "bars", 0),
                "ticks": getattr(result, "ticks", 0),
                "tick_files_ok": None,
                "tick_files_missing": None,
            }
            scenario_result["report_path"] = result.report_path
            scenario_result["errors"] = []

            # Check tick file coverage for tick model
            if scenario_settings.get("model") == 0:
                tick_coverage = self._check_tick_coverage(
                    mt5, state.symbol, scenario_settings
                )
                scenario_result["result"]["tick_files_ok"] = tick_coverage.get("ok")
                scenario_result["result"]["tick_files_missing"] = tick_coverage.get("missing")

            return scenario_result

        except Exception as e:
            scenario_result = dict(scenario)
            scenario_result["success"] = False
            scenario_result["result"] = {}
            scenario_result["errors"] = [str(e)]
            return scenario_result

    def _check_tick_coverage(
        self,
        mt5: "MT5Interface",
        symbol: str,
        scenario_settings: dict[str, Any],
    ) -> dict[str, Any]:
        """Check tick file coverage for a scenario window."""
        # This would check for .tkc files in MT5 tick storage
        # For now, return placeholder indicating check not performed
        return {"ok": None, "missing": None}

    def _compute_overlays(
        self,
        scenarios: list[dict[str, Any]],
        settings: Any,
    ) -> list[dict[str, Any]]:
        """Compute cost overlay scenarios from base results."""
        spread_pips = getattr(settings, "STRESS_OVERLAY_SPREAD_PIPS", [0.0, 1.0, 2.0, 3.0, 5.0])
        slippage_pips = getattr(settings, "STRESS_OVERLAY_SLIPPAGE_PIPS", [0.0, 1.0, 3.0])
        slippage_sides = getattr(settings, "STRESS_OVERLAY_SLIPPAGE_SIDES", 2)
        pip_to_points = getattr(settings, "PIP_TO_POINTS", 10)

        result_scenarios = list(scenarios)

        for base in scenarios:
            if base.get("variant") != "base" or not base.get("success"):
                continue

            base_result = base.get("result", {})
            base_profit = base_result.get("profit", 0)
            base_trades = base_result.get("total_trades", 0)

            if base_trades == 0:
                continue

            for spread in spread_pips:
                for slip in slippage_pips:
                    if spread == 0 and slip == 0:
                        continue  # Skip no-cost overlay

                    overlay_id = f"{base['id']}_overlay_sp{spread}_sl{slip}"

                    # Estimate cost adjustment (simplified)
                    # Real implementation would use pip value from trades
                    cost_per_trade = (spread + slip * slippage_sides) * pip_to_points
                    total_cost = cost_per_trade * base_trades
                    adjusted_profit = base_profit - total_cost

                    # Recalculate profit factor (simplified)
                    base_pf = base_result.get("profit_factor", 0)
                    if base_pf > 0 and base_profit > 0:
                        pf_ratio = adjusted_profit / base_profit if base_profit != 0 else 0
                        adjusted_pf = max(0, base_pf * pf_ratio)
                    else:
                        adjusted_pf = 0

                    overlay = {
                        "id": overlay_id,
                        "label": f"{base['label']} +{spread}sp +{slip}sl",
                        "period": base.get("period"),
                        "window": base.get("window"),
                        "tags": base.get("tags", []) + ["overlay"],
                        "variant": "overlay",
                        "base_scenario_id": base["id"],
                        "overlay_settings": {
                            "spread_pips": spread,
                            "slippage_pips": slip,
                            "slippage_sides": slippage_sides,
                        },
                        "success": True,
                        "result": {
                            "profit": adjusted_profit,
                            "profit_factor": adjusted_pf,
                            "max_drawdown_pct": base_result.get("max_drawdown_pct", 0),
                            "total_trades": base_trades,
                            "cost_adjustment": total_cost,
                        },
                        "errors": [],
                    }
                    result_scenarios.append(overlay)

        return result_scenarios
