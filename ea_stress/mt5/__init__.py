"""
MT5 Abstraction Layer

Provides interface and implementations for MT5 operations:
- MT5Interface: Protocol defining operations (compile, backtest, optimize)
- TerminalMT5: Real implementation wrapping existing modules
- DryRunMT5: Mock implementation for testing without MT5

Result types:
- CompileResult: Compilation outcome
- BacktestResult: Backtest metrics and equity curve
- OptimizationResult: Optimization passes and best results
"""

from ea_stress.mt5.interface import (
    MT5Interface,
    CompileResult,
    BacktestResult,
    OptimizationResult,
)

__all__ = [
    "MT5Interface",
    "CompileResult",
    "BacktestResult",
    "OptimizationResult",
    "TerminalMT5",
    "DryRunMT5",
]


def __getattr__(name: str):
    """Lazy import for implementations to avoid circular imports."""
    if name == "TerminalMT5":
        from ea_stress.mt5.terminal import TerminalMT5

        return TerminalMT5
    if name == "DryRunMT5":
        from ea_stress.mt5.dry_run import DryRunMT5

        return DryRunMT5
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
