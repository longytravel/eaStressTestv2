"""
MT5 Interface Protocol

Defines the interface for MT5 operations and result dataclasses.
Uses typing.Protocol for structural subtyping - implementations don't need to inherit.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Protocol, Any


@dataclass(frozen=True)
class CompileResult:
    """Result of compiling an MQL5 file."""

    success: bool
    exe_path: str | None
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "exe_path": self.exe_path,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompileResult":
        return cls(
            success=data.get("success", False),
            exe_path=data.get("exe_path"),
            errors=tuple(data.get("errors", [])),
            warnings=tuple(data.get("warnings", [])),
        )


@dataclass(frozen=True)
class BacktestResult:
    """Result of running a backtest."""

    success: bool
    profit: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    expected_payoff: float = 0.0
    recovery_factor: float = 0.0
    equity_curve: tuple[float, ...] = field(default_factory=tuple)
    report_path: str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "profit": self.profit,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "sharpe_ratio": self.sharpe_ratio,
            "expected_payoff": self.expected_payoff,
            "recovery_factor": self.recovery_factor,
            "equity_curve": list(self.equity_curve),
            "report_path": self.report_path,
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BacktestResult":
        return cls(
            success=data.get("success", False),
            profit=float(data.get("profit", 0.0)),
            profit_factor=float(data.get("profit_factor", 0.0)),
            max_drawdown_pct=float(data.get("max_drawdown_pct", 0.0)),
            total_trades=int(data.get("total_trades", 0)),
            win_rate=float(data.get("win_rate", 0.0)),
            sharpe_ratio=float(data.get("sharpe_ratio", 0.0)),
            expected_payoff=float(data.get("expected_payoff", 0.0)),
            recovery_factor=float(data.get("recovery_factor", 0.0)),
            equity_curve=tuple(data.get("equity_curve", [])),
            report_path=data.get("report_path"),
            errors=tuple(data.get("errors", [])),
        )


@dataclass(frozen=True)
class OptimizationResult:
    """Result of running an optimization."""

    success: bool
    passes_count: int = 0
    results: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    best_result: dict[str, Any] | None = None
    xml_path: str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "passes_count": self.passes_count,
            "results": list(self.results),
            "best_result": self.best_result,
            "xml_path": self.xml_path,
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OptimizationResult":
        return cls(
            success=data.get("success", False),
            passes_count=int(data.get("passes_count", 0)),
            results=tuple(data.get("results", [])),
            best_result=data.get("best_result"),
            xml_path=data.get("xml_path"),
            errors=tuple(data.get("errors", [])),
        )


class MT5Interface(Protocol):
    """Protocol defining MT5 operations.

    Uses structural subtyping - implementations don't need to inherit from this.
    Any class with matching method signatures satisfies the protocol.
    """

    def compile(self, ea_path: Path) -> CompileResult:
        """Compile an MQL5 EA.

        Args:
            ea_path: Path to the .mq5 source file

        Returns:
            CompileResult with success status, exe path, and any errors/warnings
        """
        ...

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
        """Run a backtest.

        Args:
            ea_path: Path to the .ex5 compiled EA
            symbol: Trading symbol (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "H1", "M15")
            params: Optional parameter overrides
            from_date: Optional start date (YYYY.MM.DD format)
            to_date: Optional end date (YYYY.MM.DD format)
            model: Optional tick model (0=ticks, 1=1-minute OHLC)
            report_name: Optional report filename (for deterministic naming)

        Returns:
            BacktestResult with metrics and equity curve
        """
        ...

    def optimize(
        self,
        ea_path: Path,
        symbol: str,
        timeframe: str,
        param_ranges: list[dict[str, Any]],
        report_name: str | None = None,
        timeout: int | None = None,
    ) -> OptimizationResult:
        """Run parameter optimization.

        Args:
            ea_path: Path to the .ex5 compiled EA
            symbol: Trading symbol (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "H1", "M15")
            param_ranges: List of parameter range definitions
            report_name: Optional report filename (for deterministic naming)
            timeout: Optional timeout in seconds

        Returns:
            OptimizationResult with passes and best results
        """
        ...
