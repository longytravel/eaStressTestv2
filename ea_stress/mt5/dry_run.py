"""
Dry Run MT5 Implementation

Mock implementation for testing without MT5 installed.
Configurable responses and call logging for test assertions.
"""

from pathlib import Path
from typing import Any

from ea_stress.mt5.interface import (
    CompileResult,
    BacktestResult,
    OptimizationResult,
)


class DryRunMT5:
    """Mock MT5 implementation for testing.

    Satisfies MT5Interface protocol through structural subtyping.
    Provides configurable responses and logs all method calls.
    """

    def __init__(
        self,
        compile_success: bool = True,
        compile_errors: list[str] | None = None,
        backtest_trades: int = 100,
        backtest_profit: float = 500.0,
        backtest_profit_factor: float = 1.8,
        backtest_max_drawdown_pct: float = 15.0,
        optimization_passes: int = 500,
        optimization_results: list[dict[str, Any]] | None = None,
    ):
        """Initialize with configurable mock responses.

        Args:
            compile_success: Whether compile() returns success
            compile_errors: Errors to return on compile failure
            backtest_trades: Number of trades in backtest result
            backtest_profit: Total profit in backtest result
            backtest_profit_factor: Profit factor in backtest result
            backtest_max_drawdown_pct: Max drawdown % in backtest result
            optimization_passes: Number of optimization passes
            optimization_results: Custom optimization results (or auto-generate)
        """
        self.compile_success = compile_success
        self.compile_errors = compile_errors or []
        self.backtest_trades = backtest_trades
        self.backtest_profit = backtest_profit
        self.backtest_profit_factor = backtest_profit_factor
        self.backtest_max_drawdown_pct = backtest_max_drawdown_pct
        self.optimization_passes = optimization_passes
        self.optimization_results = optimization_results

        # Call log for test assertions: list of (method_name, args_dict)
        self.call_log: list[tuple[str, dict[str, Any]]] = []

    def compile(self, ea_path: Path) -> CompileResult:
        """Mock compile - returns configured success/failure.

        Args:
            ea_path: Path to the .mq5 source file

        Returns:
            CompileResult based on configuration
        """
        self.call_log.append(("compile", {"ea_path": ea_path}))

        if self.compile_success:
            exe_path = str(Path(ea_path).with_suffix(".ex5"))
            return CompileResult(
                success=True,
                exe_path=exe_path,
                errors=tuple(),
                warnings=tuple(),
            )
        else:
            return CompileResult(
                success=False,
                exe_path=None,
                errors=tuple(self.compile_errors or ["Mock compile error"]),
                warnings=tuple(),
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
        """Mock backtest - returns configured metrics.

        Generates a simple linear equity curve from initial balance to final.

        Args:
            ea_path: Path to the .ex5 compiled EA
            symbol: Trading symbol
            timeframe: Timeframe
            params: Optional parameter overrides
            from_date: Optional start date
            to_date: Optional end date
            model: Optional tick model
            report_name: Optional report filename

        Returns:
            BacktestResult with configured metrics
        """
        self.call_log.append(
            (
                "backtest",
                {
                    "ea_path": ea_path,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "params": params,
                    "from_date": from_date,
                    "to_date": to_date,
                    "model": model,
                    "report_name": report_name,
                },
            )
        )

        # Generate simple linear equity curve
        initial_balance = 10000.0
        final_balance = initial_balance + self.backtest_profit
        num_points = max(self.backtest_trades, 10)
        step = self.backtest_profit / (num_points - 1) if num_points > 1 else 0
        equity_curve = tuple(initial_balance + step * i for i in range(num_points))

        # Calculate derived metrics
        win_rate = 55.0 if self.backtest_profit > 0 else 45.0
        sharpe = 1.5 if self.backtest_profit > 0 else 0.5
        expected_payoff = self.backtest_profit / self.backtest_trades if self.backtest_trades > 0 else 0
        recovery = abs(self.backtest_profit / (self.backtest_max_drawdown_pct * 100)) if self.backtest_max_drawdown_pct > 0 else 0

        return BacktestResult(
            success=True,
            profit=self.backtest_profit,
            profit_factor=self.backtest_profit_factor,
            max_drawdown_pct=self.backtest_max_drawdown_pct,
            total_trades=self.backtest_trades,
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            expected_payoff=expected_payoff,
            recovery_factor=recovery,
            equity_curve=equity_curve,
            report_path=None,
            errors=tuple(),
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
        """Mock optimize - returns configured or generated passes.

        If optimization_results not provided, generates N passes with
        deterministic but varied metrics based on pass index.

        Args:
            ea_path: Path to the .ex5 compiled EA
            symbol: Trading symbol
            timeframe: Timeframe
            param_ranges: List of parameter range definitions
            report_name: Optional report filename
            timeout: Optional timeout

        Returns:
            OptimizationResult with passes
        """
        self.call_log.append(
            (
                "optimize",
                {
                    "ea_path": ea_path,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "param_ranges": param_ranges,
                    "report_name": report_name,
                    "timeout": timeout,
                },
            )
        )

        if self.optimization_results is not None:
            results = self.optimization_results
        else:
            # Generate deterministic mock passes
            results = []
            for i in range(self.optimization_passes):
                # Use pass index as seed for reproducible but varied metrics
                seed = i + 1
                profit = 1000.0 - (i * 2.0)  # Best passes first
                pf = max(0.5, 2.5 - (i * 0.004))
                dd = 10.0 + (i * 0.02)
                trades = 100 + (i % 50)

                results.append(
                    {
                        "result": profit * pf,  # OnTester score
                        "profit": profit,
                        "profit_factor": pf,
                        "max_drawdown_pct": dd,
                        "total_trades": trades,
                        "sharpe_ratio": 1.5 - (i * 0.002),
                        "recovery_factor": profit / (dd * 100) if dd > 0 else 0,
                        "params": {
                            "Pass": i,
                            **{
                                p.get("name", f"param_{j}"): p.get("start", 0) + (i % 10)
                                for j, p in enumerate(param_ranges)
                                if "name" in p
                            },
                        },
                    }
                )

        best = results[0] if results else None

        return OptimizationResult(
            success=len(results) > 0,
            passes_count=len(results),
            results=tuple(results),
            best_result=best,
            xml_path=None,
            errors=tuple() if results else tuple(["No optimization passes"]),
        )
