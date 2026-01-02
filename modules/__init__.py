"""
EA Stress Test Modules

Standalone functional modules for EA testing workflow.
Each module can be used independently or orchestrated by the workflow engine.

NOTE: Parameter analysis (wide params + optimization ranges) is done by Claude
via /param-analyzer skill, NOT by Python heuristics.

NOTE: Pass selection (top 20 for backtesting) is done by Claude via
/stats-analyzer skill, NOT by Python scoring functions.

IMPORT PATTERN: To avoid circular imports when using from the engine,
import modules directly:
    from modules.compiler import compile_ea
    from modules.backtest import run_backtest
    # etc.

Or use the module-level imports below (lazy-loaded when accessed).
"""


def __getattr__(name):
    """Lazy loading to avoid circular imports."""
    if name == 'compile_ea':
        from .compiler import compile_ea
        return compile_ea
    elif name == 'extract_params':
        from .params import extract_params
        return extract_params
    elif name == 'inject_ontester':
        from .injector import inject_ontester
        return inject_ontester
    elif name == 'inject_safety':
        from .injector import inject_safety
        return inject_safety
    elif name == 'create_modified_ea':
        from .injector import create_modified_ea
        return create_modified_ea
    elif name == 'run_backtest':
        from .backtest import run_backtest
        return run_backtest
    elif name == 'run_optimization':
        from .optimizer import run_optimization
        return run_optimization
    elif name == 'parse_optimization_results':
        from .optimizer import parse_optimization_results
        return parse_optimization_results
    elif name == 'create_ini_file':
        from .optimizer import create_ini_file
        return create_ini_file
    elif name == 'run_monte_carlo':
        from .monte_carlo import run_monte_carlo
        return run_monte_carlo
    elif name == 'extract_trades_from_results':
        from .monte_carlo import extract_trades_from_results
        return extract_trades_from_results
    elif name == 'analyze_passes':
        from .pass_analyzer import analyze_passes
        return analyze_passes
    elif name == 'extract_trades':
        from .trade_extractor import extract_trades
        return extract_trades
    elif name == 'compute_equity_curve':
        from .trade_extractor import compute_equity_curve
        return compute_equity_curve
    elif name == 'split_trades_by_date':
        from .trade_extractor import split_trades_by_date
        return split_trades_by_date
    elif name == 'Trade':
        from .trade_extractor import Trade
        return Trade
    elif name == 'TradeExtractionResult':
        from .trade_extractor import TradeExtractionResult
        return TradeExtractionResult
    elif name == 'find_robust_params':
        raise AttributeError(
            "find_robust_params was REMOVED. Use Claude /stats-analyzer skill instead. "
            "See CLAUDE.md Lesson #1 for why median params are problematic."
        )
    raise AttributeError(f"module 'modules' has no attribute '{name}'")


__all__ = [
    'compile_ea',
    'extract_params',
    'inject_ontester',
    'inject_safety',
    'create_modified_ea',
    'run_backtest',
    'run_optimization',
    'parse_optimization_results',
    'create_ini_file',
    'run_monte_carlo',
    'extract_trades_from_results',
    'analyze_passes',
    'extract_trades',
    'compute_equity_curve',
    'split_trades_by_date',
    'Trade',
    'TradeExtractionResult',
    # find_robust_params deliberately omitted - deprecated
]
