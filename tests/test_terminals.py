"""
Tests for Terminal Registry

Tests terminal configuration loading, validation, and EA discovery.
"""
import pytest
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.terminals import TerminalRegistry, get_registry


class TestTerminalRegistry:
    """Tests for TerminalRegistry class."""

    def test_load_terminals(self, sample_terminals_json):
        """Test loading terminal configurations."""
        registry = TerminalRegistry(str(sample_terminals_json))

        terminals = registry.list_terminals()
        assert len(terminals) == 2

        names = [t['name'] for t in terminals]
        assert 'TestBroker' in names
        assert 'AnotherBroker' in names

    def test_filter_comment_keys(self, sample_terminals_json):
        """Test that comment/instruction keys are filtered out."""
        registry = TerminalRegistry(str(sample_terminals_json))

        terminals = registry.list_terminals()
        names = [t['name'] for t in terminals]
        assert '_comment' not in names

    def test_default_terminal(self, sample_terminals_json):
        """Test that default terminal is set correctly."""
        registry = TerminalRegistry(str(sample_terminals_json))

        assert registry.active == 'TestBroker'

        terminal = registry.get_terminal()
        assert terminal['name'] == 'TestBroker'

    def test_set_active_terminal(self, sample_terminals_json):
        """Test switching active terminal."""
        registry = TerminalRegistry(str(sample_terminals_json))

        # Switch to another broker
        terminal = registry.set_active('AnotherBroker')

        assert registry.active == 'AnotherBroker'
        assert terminal['name'] == 'AnotherBroker'

    def test_set_invalid_terminal(self, sample_terminals_json):
        """Test error when setting invalid terminal."""
        registry = TerminalRegistry(str(sample_terminals_json))

        with pytest.raises(ValueError) as exc_info:
            registry.set_active('NonExistent')

        assert 'NonExistent' in str(exc_info.value)
        assert 'TestBroker' in str(exc_info.value)

    def test_get_terminal_paths(self, sample_terminals_json):
        """Test that terminal includes derived paths."""
        registry = TerminalRegistry(str(sample_terminals_json))
        terminal = registry.get_terminal()

        assert 'experts_path' in terminal
        assert 'include_path' in terminal
        assert 'logs_path' in terminal
        assert 'files_path' in terminal

        assert 'MQL5' in terminal['experts_path']
        assert 'Experts' in terminal['experts_path']

    def test_validate_terminal_exists(self, sample_terminals_json):
        """Test validation when terminal exists."""
        registry = TerminalRegistry(str(sample_terminals_json))
        result = registry.validate_terminal()

        assert result['valid'] == True
        assert len(result['issues']) == 0

    def test_validate_terminal_missing(self, sample_terminals_json):
        """Test validation when terminal files missing."""
        registry = TerminalRegistry(str(sample_terminals_json))

        # AnotherBroker has no actual files
        result = registry.validate_terminal('AnotherBroker')

        assert result['valid'] == False
        assert len(result['issues']) > 0

    def test_find_eas(self, sample_terminals_json, temp_dir):
        """Test finding EA files."""
        registry = TerminalRegistry(str(sample_terminals_json))

        # Create some EA files
        experts_path = temp_dir / "data" / "MQL5" / "Experts"
        (experts_path / "TestEA.mq5").touch()
        (experts_path / "AnotherEA.mq5").touch()
        (experts_path / "NotAnEA.txt").touch()

        eas = registry.find_eas()

        assert len(eas) == 2
        names = [ea['name'] for ea in eas]
        assert 'TestEA' in names
        assert 'AnotherEA' in names

    def test_find_eas_in_subfolders(self, sample_terminals_json, temp_dir):
        """Test finding EAs in subfolders."""
        registry = TerminalRegistry(str(sample_terminals_json))

        experts_path = temp_dir / "data" / "MQL5" / "Experts"
        subfolder = experts_path / "MyFolder"
        subfolder.mkdir()
        (subfolder / "SubEA.mq5").touch()

        eas = registry.find_eas()

        names = [ea['name'] for ea in eas]
        assert 'SubEA' in names

    def test_missing_config_file(self, temp_dir):
        """Test error when config file missing."""
        with pytest.raises(FileNotFoundError):
            TerminalRegistry(str(temp_dir / "nonexistent.json"))

    def test_get_registry_helper(self, sample_terminals_json):
        """Test convenience function."""
        registry = get_registry(str(sample_terminals_json))

        assert isinstance(registry, TerminalRegistry)
        assert registry.active == 'TestBroker'
