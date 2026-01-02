"""
Module loader utility to avoid circular imports.

This module provides a function to load modules directly by file path,
bypassing the normal import system. This is needed because modules/__init__.py
uses lazy loading with __getattr__, which can cause circular import issues
when engine or reports modules try to import from modules.

Usage:
    from modules.loader import load_module

    pass_analyzer = load_module("pass_analyzer", "modules/pass_analyzer.py")
    analyze_passes = pass_analyzer.analyze_passes
"""

import importlib.util
from pathlib import Path

# Cache loaded modules to avoid reloading
_module_cache: dict = {}


def load_module(name: str, path):
    """
    Load a module directly from file path.

    Args:
        name: Module name (used for caching)
        path: Path to the .py file (relative or absolute)

    Returns:
        The loaded module
    """
    # Normalize path
    path = Path(path)
    if not path.is_absolute():
        # Make relative to project root
        path = Path(__file__).parent.parent / path

    # Check cache
    cache_key = str(path)
    if cache_key in _module_cache:
        return _module_cache[cache_key]

    # Check file exists
    if not path.exists():
        raise ImportError(f"Module file not found: {path}")

    # Load module
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Cache and return
    _module_cache[cache_key] = module
    return module


def get_modules_dir() -> Path:
    """Get the path to the modules directory."""
    return Path(__file__).parent
