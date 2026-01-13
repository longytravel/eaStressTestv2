"""
Stage 8: Parse Optimization Results

Parse MT5 optimization XML results and filter by minimum trades.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class ParseResultsStage:
    """Stage 8: Parse optimization XML results and filter valid passes."""

    @property
    def name(self) -> str:
        return "8_parse_results"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Parse optimization results from XML.

        Requires:
            - Step 7 (run_optimization) completed with xml_path

        Args:
            state: Current workflow state
            mt5: Not required for this stage

        Returns:
            StageResult with parsed passes and gate check
        """
        from ea_stress.core.metrics import GateResult

        # Get xml_path from Step 7
        step_7 = state.steps.get("7_run_optimization")
        if not step_7 or not step_7.passed or not step_7.result:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("Step 7 (run_optimization) must complete successfully first",),
            )

        xml_path = step_7.result.get("xml_path")
        if not xml_path:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=("No xml_path from Step 7",),
            )

        forward_xml_path = step_7.result.get("forward_xml_path")

        # Parse XML
        try:
            passes = self._parse_xml(xml_path)
        except Exception as e:
            return StageResult(
                success=False,
                data={},
                gate=None,
                errors=(f"Failed to parse XML: {e}",),
            )

        # Merge forward results if available
        if forward_xml_path and Path(forward_xml_path).exists():
            try:
                forward_passes = self._parse_xml(forward_xml_path)
                self._merge_forward_results(passes, forward_passes)
            except Exception:
                pass  # Forward merge is optional

        # Import settings for threshold
        import settings

        # Use ONTESTER_MIN_TRADES (lower threshold for genetic exploration)
        min_trades = getattr(settings, "ONTESTER_MIN_TRADES", 10)

        # Filter by minimum trades
        valid_passes = [
            p for p in passes
            if p.get("total_trades", 0) >= min_trades
        ]

        # Identify consistent passes (both back and forward positive)
        consistent_passes = []
        for p in valid_passes:
            params = p.get("params", {})
            back_result = params.get("Back Result", p.get("profit", 0))
            forward_result = params.get("Forward Result", 0)
            if back_result > 0 and forward_result > 0:
                consistent_passes.append(p)

        # Gate: At least one valid pass
        gate = GateResult(
            name="valid_passes",
            passed=len(valid_passes) >= 1,
            value=len(valid_passes),
            threshold=1,
            operator=">=",
        )

        data = {
            "total_passes": len(passes),
            "valid_passes": len(valid_passes),
            "passes": valid_passes,
            "consistent_passes": len(consistent_passes),
            "min_trades_filter": min_trades,
        }

        if gate.passed:
            return StageResult(
                success=True,
                data=data,
                gate=gate,
                errors=(),
            )
        else:
            return StageResult(
                success=False,
                data=data,
                gate=gate,
                errors=(f"No passes with >= {min_trades} trades",),
            )

    def _parse_xml(self, xml_path: str) -> list[dict[str, Any]]:
        """Parse MT5 Excel Spreadsheet ML format XML.

        Args:
            xml_path: Path to optimization XML

        Returns:
            List of pass dictionaries with normalized field names
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        passes = []
        headers: list[str] = []

        # Find all rows - try with namespace first, then without
        rows = root.findall(".//{urn:schemas-microsoft-com:office:spreadsheet}Row")
        if not rows:
            rows = root.findall(".//Row")

        for i, row in enumerate(rows):
            # Get cells - try with namespace first
            cells = row.findall("{urn:schemas-microsoft-com:office:spreadsheet}Cell")
            if not cells:
                cells = row.findall("Cell")

            cell_values: list[Any] = []
            for cell in cells:
                # Get Data element
                data = cell.find("{urn:schemas-microsoft-com:office:spreadsheet}Data")
                if data is None:
                    data = cell.find("Data")

                if data is not None and data.text:
                    value = data.text
                    # Try to convert to number
                    try:
                        if "." in value:
                            cell_values.append(float(value))
                        else:
                            cell_values.append(int(value))
                    except ValueError:
                        cell_values.append(value)
                else:
                    cell_values.append(None)

            if i == 0:
                # First row is headers
                headers = [str(v) if v else f"col_{j}" for j, v in enumerate(cell_values)]
            elif cell_values:
                # Data row
                pass_data = dict(zip(headers, cell_values))
                if pass_data:
                    passes.append(self._normalize_pass_data(pass_data))

        # Sort by Result (OnTester return value) descending
        passes.sort(key=lambda x: x.get("result", x.get("profit", 0)), reverse=True)

        return passes

    def _normalize_pass_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize field names from XML to standard names."""
        # Common field mappings (MT5 XML uses various names)
        mappings = {
            "Result": "result",
            "Profit": "profit",
            "Profit Factor": "profit_factor",
            "ProfitFactor": "profit_factor",
            "Expected Payoff": "expected_payoff",
            "ExpectedPayoff": "expected_payoff",
            "Equity DD %": "max_drawdown_pct",
            "Drawdown %": "max_drawdown_pct",
            "Equity Drawdown %": "max_drawdown_pct",
            "Trades": "total_trades",
            "Total Trades": "total_trades",
            "Sharpe Ratio": "sharpe_ratio",
            "SharpeRatio": "sharpe_ratio",
            "Sortino Ratio": "sortino_ratio",
            "Recovery Factor": "recovery_factor",
            "RecoveryFactor": "recovery_factor",
            "Win %": "win_rate",
            "Profit Trades %": "win_rate",
        }

        normalized: dict[str, Any] = {}
        params: dict[str, Any] = {}

        for key, value in data.items():
            # Check if it's a known metric
            if key in mappings:
                normalized[mappings[key]] = value
            elif key.lower() in [m.lower() for m in mappings.keys()]:
                # Case-insensitive match
                for orig, mapped in mappings.items():
                    if key.lower() == orig.lower():
                        normalized[mapped] = value
                        break
            else:
                # Assume it's a parameter
                params[key] = value

        normalized["params"] = params

        # Ensure required fields exist
        if "result" not in normalized:
            normalized["result"] = normalized.get("profit", 0)

        return normalized

    def _merge_forward_results(
        self,
        base_results: list[dict[str, Any]],
        forward_results: list[dict[str, Any]],
    ) -> None:
        """Merge forward report data into main optimization results.

        The main report contains the back/in-sample segment.
        The forward report contains forward segment plus result columns.
        """
        forward_by_pass: dict[int, dict[str, Any]] = {}

        for p in forward_results:
            params = p.get("params") or {}
            pass_num = params.get("Pass")
            if isinstance(pass_num, int):
                forward_by_pass[pass_num] = p

        for p in base_results:
            params = p.get("params") or {}
            pass_num = params.get("Pass")
            if not isinstance(pass_num, int):
                continue

            # Ensure 'Back Result' exists even if forward report isn't found
            if "Back Result" not in params:
                params["Back Result"] = p.get("result", 0)

            fwd = forward_by_pass.get(pass_num)
            if not fwd:
                continue

            fwd_params = fwd.get("params") or {}

            # Attach criterion breakdown into params
            if "Forward Result" in fwd_params:
                params["Forward Result"] = fwd_params["Forward Result"]
            if "Back Result" in fwd_params:
                params["Back Result"] = fwd_params["Back Result"]

            # Attach forward-segment metrics
            p["forward_profit"] = fwd.get("profit", 0)
            p["forward_expected_payoff"] = fwd.get("expected_payoff", 0)
            p["forward_profit_factor"] = fwd.get("profit_factor", 0)
            p["forward_recovery_factor"] = fwd.get("recovery_factor", 0)
            p["forward_sharpe_ratio"] = fwd.get("sharpe_ratio", 0)
            p["forward_max_drawdown_pct"] = fwd.get("max_drawdown_pct", 0)
            p["forward_total_trades"] = fwd.get("total_trades", 0)

            # Trade counts are additive across segments
            try:
                p["total_trades"] = (
                    int(p.get("total_trades", 0) or 0)
                    + int(fwd.get("total_trades", 0) or 0)
                )
            except (TypeError, ValueError):
                pass  # Keep original if any weirdness in types
