"""
Stage 14: Multi-Pair

Prepare metadata for running the workflow on additional trading symbols.
Returns orchestration data for the pipeline (cannot instantiate WorkflowRunner from stage).
"""

from typing import TYPE_CHECKING, Any

from ea_stress.stages.base import StageResult

if TYPE_CHECKING:
    from ea_stress.core.state import WorkflowState
    from ea_stress.mt5.interface import MT5Interface


class MultiPairStage:
    """Stage 14: Prepare multi-pair workflow orchestration metadata."""

    @property
    def name(self) -> str:
        return "14_multi_pair"

    def execute(
        self,
        state: "WorkflowState",
        mt5: "MT5Interface | None" = None,
    ) -> StageResult:
        """Prepare multi-pair orchestration data.

        This stage returns metadata for pipeline orchestration rather than
        executing child workflows directly (cannot instantiate WorkflowRunner
        from within a stage).

        Requires:
            - Step 4 (analyze_params) completed with params/ranges

        Returns:
            StageResult with:
                - skipped: True if no additional symbols
                - symbols: List of symbols to test
                - parent_params: wide_validation_params and optimization_ranges
                - runs: Empty list (populated by pipeline after execution)

        Args:
            state: Current workflow state
            mt5: MT5 interface (not used - orchestration only)

        Returns:
            StageResult with orchestration metadata (informational, no gate)
        """
        import settings

        # Get configured symbols
        symbols = getattr(settings, "MULTI_PAIR_SYMBOLS", ["EURUSD", "USDJPY"])
        if not symbols:
            symbols = []

        # Filter out parent symbol (case-insensitive)
        parent_symbol = state.symbol.upper() if state.symbol else ""
        additional_symbols = [s for s in symbols if s.upper() != parent_symbol]

        # Skip if no additional symbols
        if not additional_symbols:
            return StageResult(
                success=True,
                data={
                    "skipped": True,
                    "reason": "No additional symbols configured",
                    "symbols": [],
                    "runs": [],
                },
                gate=None,
                errors=(),
            )

        # Check for stored params/ranges from Step 4
        step_4 = state.steps.get("4_analyze_params")
        if not step_4 or not step_4.passed or not step_4.result:
            return StageResult(
                success=True,
                data={
                    "skipped": True,
                    "reason": "No stored params/ranges available for multi-pair",
                    "symbols": additional_symbols,
                    "runs": [],
                },
                gate=None,
                errors=(),
            )

        wide_validation_params = step_4.result.get("wide_validation_params")
        optimization_ranges = step_4.result.get("optimization_ranges")

        if not wide_validation_params or not optimization_ranges:
            return StageResult(
                success=True,
                data={
                    "skipped": True,
                    "reason": "No stored params/ranges available for multi-pair",
                    "symbols": additional_symbols,
                    "runs": [],
                },
                gate=None,
                errors=(),
            )

        # Return orchestration metadata for pipeline
        return StageResult(
            success=True,
            data={
                "skipped": False,
                "symbol_count": len(additional_symbols),
                "symbols": additional_symbols,
                "parent_params": {
                    "wide_validation_params": wide_validation_params,
                    "optimization_ranges": optimization_ranges,
                },
                "runs": [],  # Populated by pipeline after execution
            },
            gate=None,
            errors=(),
        )
