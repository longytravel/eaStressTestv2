"""Tests for modules.loader utility."""

import sys
from pathlib import Path
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.loader import load_module, get_modules_dir


class TestLoadModule:
    """Test load_module function."""

    def test_load_existing_module(self):
        """Test loading an existing module."""
        # Load the pass_analyzer module
        mod = load_module("pass_analyzer", "modules/pass_analyzer.py")
        assert hasattr(mod, 'analyze_passes')

    def test_load_with_absolute_path(self):
        """Test loading with absolute path."""
        modules_dir = get_modules_dir()
        mod = load_module("params", modules_dir / "params.py")
        assert hasattr(mod, 'extract_params')

    def test_module_caching(self):
        """Test that modules are cached."""
        mod1 = load_module("compiler", "modules/compiler.py")
        mod2 = load_module("compiler", "modules/compiler.py")
        # Should be the exact same object due to caching
        assert mod1 is mod2

    def test_load_nonexistent_module(self):
        """Test loading a non-existent module."""
        with pytest.raises(ImportError):
            load_module("nonexistent", "modules/nonexistent_module.py")


class TestGetModulesDir:
    """Test get_modules_dir function."""

    def test_returns_path(self):
        """Test that get_modules_dir returns a Path."""
        modules_dir = get_modules_dir()
        assert isinstance(modules_dir, Path)

    def test_directory_exists(self):
        """Test that the modules directory exists."""
        modules_dir = get_modules_dir()
        assert modules_dir.exists()
        assert modules_dir.is_dir()

    def test_contains_modules(self):
        """Test that the directory contains expected modules."""
        modules_dir = get_modules_dir()
        expected_files = ['compiler.py', 'backtest.py', 'params.py', 'loader.py']
        for filename in expected_files:
            assert (modules_dir / filename).exists(), f"Missing {filename}"
