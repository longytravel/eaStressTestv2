"""
Terminal MT5 Implementation

Wraps existing modules (compiler, backtest, optimizer) behind the MT5Interface.
This is a thin adapter that converts untyped dict responses to typed dataclasses.
"""

from pathlib import Path
from typing import Any

from ea_stress.mt5.interface import (
    CompileResult,
    BacktestResult,
    OptimizationResult,
)


class TerminalMT5:
    """MT5 implementation using real terminal via existing modules.

    Satisfies MT5Interface protocol through structural subtyping.
    """

    def compile(self, ea_path: Path) -> CompileResult:
        """Compile an MQL5 EA using MetaEditor64.

        Args:
            ea_path: Path to the .mq5 source file

        Returns:
            CompileResult with success status and any errors/warnings
        """
        from modules.compiler import compile_ea

        result = compile_ea(str(ea_path))

        return CompileResult(
            success=result.get("success", False),
            exe_path=result.get("exe_path"),
            errors=tuple(result.get("errors", [])),
            warnings=tuple(result.get("warnings", [])),
        )

    def backtest(
        self,
        ea_path: Path,
        symbol: str,
        timeframe: str,
        params: dict[str, Any] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        model: int | None = None,
        report_name: str | None = None,
    ) -> BacktestResult:
        """Run a backtest using MT5 terminal.

        Args:
            ea_path: Path to the .ex5 compiled EA
            symbol: Trading symbol (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "H1", "M15")
            params: Optional parameter overrides
            from_date: Optional start date (YYYY.MM.DD format)
            to_date: Optional end date (YYYY.MM.DD format)
            model: Optional tick model (0=ticks, 1=1-minute OHLC)
            report_name: Optional report filename

        Returns:
            BacktestResult with metrics and equity curve
        """
        from modules.backtest import run_backtest

        result = run_backtest(
            ea_path=str(ea_path),
            symbol=symbol,
            timeframe=timeframe,
            params=params,
            from_date=from_date,
            to_date=to_date,
            model=model,
            report_name=report_name,
        )

        return BacktestResult(
            success=result.get("success", False),
            profit=float(result.get("profit", 0.0) or 0.0),
            profit_factor=float(result.get("profit_factor", 0.0) or 0.0),
            max_drawdown_pct=float(result.get("max_drawdown_pct", 0.0) or 0.0),
            total_trades=int(result.get("total_trades", 0) or 0),
            win_rate=float(result.get("win_rate", 0.0) or 0.0),
            sharpe_ratio=float(result.get("sharpe_ratio", 0.0) or 0.0),
            expected_payoff=float(result.get("expected_payoff", 0.0) or 0.0),
            recovery_factor=float(result.get("recovery_factor", 0.0) or 0.0),
            equity_curve=tuple(result.get("equity_curve", [])),
            report_path=result.get("report_path"),
            errors=tuple(result.get("errors", [])),
        )

    def optimize(
        self,
        ea_path: Path,
        symbol: str,
        timeframe: str,
        param_ranges: list[dict[str, Any]],
        report_name: str | None = None,
        timeout: int | None = None,
    ) -> OptimizationResult:
        """Run parameter optimization using MT5 terminal.

        Args:
            ea_path: Path to the .ex5 compiled EA
            symbol: Trading symbol (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "H1", "M15")
            param_ranges: List of parameter range definitions
            report_name: Optional report filename
            timeout: Optional timeout in seconds

        Returns:
            OptimizationResult with passes and best results
        """
        from modules.optimizer import run_optimization

        result = run_optimization(
            ea_path=str(ea_path),
            symbol=symbol,
            timeframe=timeframe,
            param_ranges=param_ranges,
            report_name=report_name,
            timeout=timeout,
        )

        return OptimizationResult(
            success=result.get("success", False),
            passes_count=int(result.get("passes", 0) or 0),
            results=tuple(result.get("results", [])),
            best_result=result.get("best_result"),
            xml_path=result.get("xml_path"),
            errors=tuple(result.get("errors", [])),
        )
