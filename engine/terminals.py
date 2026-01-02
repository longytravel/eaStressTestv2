"""
Terminal Registry Manager

Manages multiple MT5 terminal configurations for the stress test system.
"""
import json
import os
from pathlib import Path
from typing import Optional


class TerminalRegistry:
    """Manages MT5 terminal configurations."""

    def __init__(self, config_path: str = "terminals.json"):
        self.config_path = Path(config_path)
        self.terminals = {}
        self._active_terminal = None
        self._load()

    def _load(self) -> None:
        """Load terminal configurations from JSON file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Terminal config not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            data = json.load(f)

        # Filter out comment/instruction keys
        self.terminals = {
            name: config for name, config in data.items()
            if not name.startswith('_')
        }

        # Set default terminal as active
        for name, config in self.terminals.items():
            if config.get('default', False):
                self._active_terminal = name
                break

    def list_terminals(self) -> list[dict]:
        """List all configured terminals with their status."""
        result = []
        for name, config in self.terminals.items():
            terminal_path = Path(config['path'])
            data_path = Path(config['data_path'])

            result.append({
                'name': name,
                'path': config['path'],
                'data_path': config['data_path'],
                'exists': terminal_path.exists(),
                'data_exists': data_path.exists(),
                'default': config.get('default', False),
                'active': name == self._active_terminal
            })
        return result

    def get_terminal(self, name: Optional[str] = None) -> dict:
        """Get terminal configuration by name, or active terminal if none specified."""
        if name is None:
            name = self._active_terminal

        if name is None:
            raise ValueError("No terminal specified and no default terminal set")

        if name not in self.terminals:
            raise ValueError(f"Terminal not found: {name}. Available: {list(self.terminals.keys())}")

        config = self.terminals[name]
        return {
            'name': name,
            'path': config['path'],
            'data_path': config['data_path'],
            'experts_path': str(Path(config['data_path']) / 'MQL5' / 'Experts'),
            'include_path': str(Path(config['data_path']) / 'MQL5' / 'Include'),
            'logs_path': str(Path(config['data_path']) / 'MQL5' / 'Logs'),
            'files_path': str(Path(config['data_path']) / 'MQL5' / 'Files'),
        }

    def set_active(self, name: str) -> dict:
        """Set the active terminal for this session."""
        if name not in self.terminals:
            raise ValueError(f"Terminal not found: {name}. Available: {list(self.terminals.keys())}")

        self._active_terminal = name
        return self.get_terminal(name)

    @property
    def active(self) -> Optional[str]:
        """Get the name of the currently active terminal."""
        return self._active_terminal

    def validate_terminal(self, name: Optional[str] = None) -> dict:
        """Validate that a terminal is properly configured and accessible."""
        terminal = self.get_terminal(name)

        issues = []

        # Check terminal executable
        if not Path(terminal['path']).exists():
            issues.append(f"Terminal executable not found: {terminal['path']}")

        # Check data path
        if not Path(terminal['data_path']).exists():
            issues.append(f"Data path not found: {terminal['data_path']}")

        # Check Experts folder
        if not Path(terminal['experts_path']).exists():
            issues.append(f"Experts folder not found: {terminal['experts_path']}")

        return {
            'valid': len(issues) == 0,
            'terminal': terminal,
            'issues': issues
        }

    def find_eas(self, name: Optional[str] = None) -> list[dict]:
        """Find all .mq5 EA files in the terminal's Experts folder."""
        terminal = self.get_terminal(name)
        experts_path = Path(terminal['experts_path'])

        if not experts_path.exists():
            return []

        eas = []
        for mq5_file in experts_path.rglob('*.mq5'):
            # Skip files in subfolders that are clearly not EAs
            relative = mq5_file.relative_to(experts_path)

            eas.append({
                'name': mq5_file.stem,
                'filename': mq5_file.name,
                'path': str(mq5_file),
                'relative_path': str(relative),
                'modified': mq5_file.stat().st_mtime,
            })

        # Sort by modification time, newest first
        eas.sort(key=lambda x: x['modified'], reverse=True)
        return eas


# Convenience function for quick access
def get_registry(config_path: str = "terminals.json") -> TerminalRegistry:
    """Get a terminal registry instance."""
    return TerminalRegistry(config_path)
