"""
EA Compiler Module

Compiles MQL5 Expert Advisors using MetaEditor64.
"""
import subprocess
import re
from pathlib import Path
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from engine.terminals import TerminalRegistry


def compile_ea(
    ea_path: str,
    terminal: Optional[dict] = None,
    registry: Optional[TerminalRegistry] = None,
    include_path: Optional[str] = None,
) -> dict:
    """
    Compile an MQL5 EA using MetaEditor64.

    Args:
        ea_path: Path to the .mq5 file
        terminal: Terminal config dict (from registry.get_terminal())
        registry: TerminalRegistry instance (used if terminal not provided)
        include_path: Optional custom include path

    Returns:
        dict with keys:
            - success: bool
            - exe_path: str (path to compiled .ex5 if successful)
            - errors: list of error strings
            - warnings: list of warning strings
            - output: raw compiler output
    """
    ea_path = Path(ea_path)

    if not ea_path.exists():
        return {
            'success': False,
            'exe_path': None,
            'errors': [f"EA file not found: {ea_path}"],
            'warnings': [],
            'output': '',
        }

    # Get terminal config
    if terminal is None:
        if registry is None:
            registry = TerminalRegistry()
        terminal = registry.get_terminal()

    # Find MetaEditor64.exe (same directory as terminal64.exe)
    terminal_path = Path(terminal['path'])
    metaeditor_path = terminal_path.parent / 'MetaEditor64.exe'

    if not metaeditor_path.exists():
        return {
            'success': False,
            'exe_path': None,
            'errors': [f"MetaEditor64.exe not found at: {metaeditor_path}"],
            'warnings': [],
            'output': '',
        }

    # Build compile command
    # MetaEditor64.exe /compile:"path\to\file.mq5" /log /inc:"include_path"
    cmd = [
        str(metaeditor_path),
        f'/compile:{ea_path}',
        '/log',
    ]

    # Only add /inc if explicitly provided - MetaEditor finds includes
    # automatically when EA is in terminal's Experts folder
    if include_path:
        cmd.append(f'/inc:{include_path}')

    # Run compiler
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ea_path.parent),
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'exe_path': None,
            'errors': ['Compilation timed out after 60 seconds'],
            'warnings': [],
            'output': '',
        }
    except Exception as e:
        return {
            'success': False,
            'exe_path': None,
            'errors': [f'Compilation failed: {str(e)}'],
            'warnings': [],
            'output': '',
        }

    # Parse output for errors and warnings
    errors = []
    warnings = []

    # Also check the log file if it exists
    log_path = ea_path.with_suffix('.log')
    log_content = ''
    if log_path.exists():
        try:
            log_content = log_path.read_text(encoding='utf-16-le', errors='ignore')
        except:
            try:
                log_content = log_path.read_text(encoding='utf-8', errors='ignore')
            except:
                pass

    combined_output = output + '\n' + log_content

    # Parse errors and warnings from output
    for line in combined_output.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Error patterns: "filename.mq5(123,45) : error 123: message"
        if ' : error ' in line.lower() or ': error ' in line.lower():
            errors.append(line)
        elif ' : warning ' in line.lower() or ': warning ' in line.lower():
            warnings.append(line)

    # Check if .ex5 file was created
    exe_path = ea_path.with_suffix('.ex5')
    success = exe_path.exists() and len(errors) == 0

    # If no explicit errors but exe doesn't exist, add generic error
    if not success and not errors:
        if not exe_path.exists():
            errors.append('Compilation failed: .ex5 file not created')

    return {
        'success': success,
        'exe_path': str(exe_path) if success else None,
        'errors': errors,
        'warnings': warnings,
        'output': combined_output,
    }


def get_compiler_version(terminal: Optional[dict] = None) -> Optional[str]:
    """Get MetaEditor version string."""
    if terminal is None:
        registry = TerminalRegistry()
        terminal = registry.get_terminal()

    terminal_path = Path(terminal['path'])
    metaeditor_path = terminal_path.parent / 'MetaEditor64.exe'

    if not metaeditor_path.exists():
        return None

    try:
        result = subprocess.run(
            [str(metaeditor_path), '/version'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except:
        return None
