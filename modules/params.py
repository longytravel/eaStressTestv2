"""
EA Parameter Extractor Module

Extracts input parameters from MQL5 source files.
"""
import re
from pathlib import Path
from typing import Optional


# MQL5 type mappings
MQL5_TYPES = {
    'int': 'int',
    'uint': 'int',
    'long': 'int',
    'ulong': 'int',
    'short': 'int',
    'ushort': 'int',
    'char': 'int',
    'uchar': 'int',
    'double': 'double',
    'float': 'double',
    'bool': 'bool',
    'string': 'string',
    'datetime': 'datetime',
    'color': 'color',
    'ENUM_TIMEFRAMES': 'enum',
    'ENUM_APPLIED_PRICE': 'enum',
    'ENUM_MA_METHOD': 'enum',
    'ENUM_ORDER_TYPE': 'enum',
    'ENUM_POSITION_TYPE': 'enum',
}


def extract_params(ea_path: str) -> list[dict]:
    """
    Extract input parameters from an MQL5 EA source file.

    Args:
        ea_path: Path to the .mq5 file

    Returns:
        List of dicts, each with keys:
            - name: parameter name
            - type: MQL5 type
            - base_type: normalized type (int, double, bool, string, enum)
            - default: default value (as string)
            - comment: inline comment if any
            - line: line number in source
            - optimizable: bool - can this param be optimized?
    """
    ea_path = Path(ea_path)

    if not ea_path.exists():
        raise FileNotFoundError(f"EA file not found: {ea_path}")

    content = ea_path.read_text(encoding='utf-8', errors='ignore')
    lines = content.split('\n')

    params = []

    # Pattern for input declarations:
    # input int MyParam = 10; // Comment
    # input double Lots = 0.1;
    # sinput string Comment = "test"; // Static input (not optimizable)
    input_pattern = re.compile(
        r'^[\s]*(sinput|input)\s+'  # input or sinput keyword
        r'([\w\s]+?)\s+'            # type (may include ENUM_)
        r'(\w+)\s*'                 # parameter name
        r'(?:=\s*([^;/]+?))?'       # optional default value
        r'\s*;'                     # semicolon
        r'(?:\s*//\s*(.*))?$',      # optional comment
        re.MULTILINE
    )

    for line_num, line in enumerate(lines, 1):
        # Skip commented lines
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('/*'):
            continue

        match = input_pattern.match(line)
        if match:
            input_type = match.group(1)  # 'input' or 'sinput'
            mql_type = match.group(2).strip()
            name = match.group(3).strip()
            default = match.group(4).strip() if match.group(4) else None
            comment = match.group(5).strip() if match.group(5) else None

            # Determine base type
            base_type = 'string'  # default
            mql_type_lower = mql_type.lower()

            for mql_t, base_t in MQL5_TYPES.items():
                if mql_t.lower() == mql_type_lower:
                    base_type = base_t
                    break

            # Check for enum types
            if mql_type.startswith('ENUM_') or mql_type.isupper():
                base_type = 'enum'

            # sinput = static input, not optimizable
            optimizable = (input_type == 'input') and (base_type in ['int', 'double'])

            # Injected safety params must never be optimized
            if name.startswith('EAStressSafety_'):
                optimizable = False

            params.append({
                'name': name,
                'type': mql_type,
                'base_type': base_type,
                'default': default,
                'comment': comment,
                'line': line_num,
                'optimizable': optimizable,
            })

    return params


def get_optimizable_params(ea_path: str) -> list[dict]:
    """Get only parameters that can be optimized (numeric inputs)."""
    all_params = extract_params(ea_path)
    return [p for p in all_params if p['optimizable']]


def format_params_table(params: list[dict]) -> str:
    """Format parameters as a readable table."""
    if not params:
        return "No input parameters found."

    lines = []
    lines.append(f"{'Name':<25} {'Type':<20} {'Default':<15} {'Optimizable'}")
    lines.append("-" * 75)

    for p in params:
        opt = "Yes" if p['optimizable'] else "No"
        default = p['default'] or '-'
        lines.append(f"{p['name']:<25} {p['type']:<20} {default:<15} {opt}")

    return '\n'.join(lines)


# =============================================================================
# PARAMETER ANALYSIS IS DONE BY CLAUDE
# =============================================================================
#
# The Python heuristic functions have been REMOVED.
# Parameter analysis MUST be done by Claude via /param-analyzer skill.
#
# Claude reads the EA source code, understands each parameter's purpose,
# and generates:
#   1. wide_validation_params - to maximize trades for validation
#   2. optimization_ranges - intelligent ranges for optimization
#
# This is invoked via: runner.continue_with_params(wide_params, opt_ranges)
# =============================================================================
