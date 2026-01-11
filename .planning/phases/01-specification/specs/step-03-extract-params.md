# Step 3: Extract Params

## Overview

Extracts all `input` parameters from the EA source code, producing a list of parameter definitions with types, defaults, and optimizability flags.

**This is a workflow pause point.** After extraction, the workflow waits for `/param-analyzer` to produce optimization ranges.

## Inputs

| Name | Type | Source | Description |
|------|------|--------|-------------|
| `source_path` | `str` | `runner.modified_ea_path` or `runner.ea_path` | Path to `.mq5` source |

## Outputs

| Name | Type | Destination | Description |
|------|------|-------------|-------------|
| `params` | `list[dict]` | Step result, `runner.params` | Extracted parameter definitions |
| `count` | `int` | Step result | Total parameter count |
| `optimizable` | `int` | Step result | Count of optimizable params |
| `gate` | `dict` | Step result, `state.gates` | Gate result object |

**Result structure:**
```python
{
    'params': [
        {
            'name': 'Lots',
            'type': 'double',
            'base_type': 'double',
            'default': '0.1',
            'comment': 'Lot size for trades',
            'line': 15,
            'optimizable': True
        },
        {
            'name': 'MagicNumber',
            'type': 'int',
            'base_type': 'int',
            'default': '12345',
            'comment': 'Magic number',
            'line': 16,
            'optimizable': True
        },
        {
            'name': 'Comment',
            'type': 'string',
            'base_type': 'string',
            'default': '"MyEA"',
            'comment': None,
            'line': 17,
            'optimizable': False  # strings can't be optimized
        }
    ],
    'count': 3,
    'optimizable': 2,
    'gate': {
        'name': 'params_found',
        'passed': True,
        'value': 3,
        'threshold': 1,
        'operator': '>=',
        'message': 'PASS: Found 3 parameters (2 optimizable)'
    }
}
```

### Parameter Object Schema

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Parameter name (identifier) |
| `type` | `str` | MQL5 type as written (e.g., `double`, `ENUM_TIMEFRAMES`) |
| `base_type` | `str` | Normalized type: `int`, `double`, `bool`, `string`, `enum`, `datetime`, `color` |
| `default` | `str` or `None` | Default value as string (includes quotes for strings) |
| `comment` | `str` or `None` | Inline comment after semicolon |
| `line` | `int` | Line number in source (1-indexed) |
| `optimizable` | `bool` | Whether parameter can be optimized |

**Optimizability rules:**
- `input` + numeric type (`int`, `double`) → optimizable
- `sinput` (static input) → NOT optimizable
- `string`, `bool`, `enum` → NOT optimizable
- `EAStressSafety_*` prefix → NOT optimizable (injected safety)

## Gate

| Gate Name | Condition | Threshold | Operator |
|-----------|-----------|-----------|----------|
| `params_found` | Parameter count | `1` | `>=` |

**Pass condition:** At least one parameter extracted.

**Fail condition:** No parameters found (EA has no `input` declarations).

## Implementation Notes

**Source:** `engine/runner.py:1493-1510`

```python
def _step_extract_params(self) -> tuple[bool, dict]:
    """Step 3: Extract input parameters."""
    try:
        source_path = self.modified_ea_path or str(self.ea_path)
        self.params = extract_params(str(source_path))
    except Exception as e:
        return False, {'error': str(e)}

    gate = gates.check_params_found(self.params)
    self.state.update_gates({'params_found': gate.to_dict()})

    return gate.passed, {
        'params': self.params,
        'count': len(self.params),
        'optimizable': sum(1 for p in self.params if p.get('optimizable')),
        'gate': gate.to_dict(),
    }
```

**Extractor module:** `modules/params.py:35-120`

### Extraction Logic

**Input pattern:** `modules/params.py:66-74`

```python
input_pattern = re.compile(
    r'^[\s]*(sinput|input)\s+'  # input or sinput keyword
    r'([\w\s]+?)\s+'            # type (may include ENUM_)
    r'(\w+)\s*'                 # parameter name
    r'(?:=\s*([^;/]+?))?'       # optional default value
    r'\s*;'                     # semicolon
    r'(?:\s*//\s*(.*))?$',      # optional comment
    re.MULTILINE
)
```

**Type normalization:** `modules/params.py:11-32`

```python
MQL5_TYPES = {
    'int': 'int', 'uint': 'int', 'long': 'int', ...
    'double': 'double', 'float': 'double',
    'bool': 'bool',
    'string': 'string',
    'datetime': 'datetime',
    'color': 'color',
    'ENUM_*': 'enum',
}
```

**Optimizability determination:** `modules/params.py:103-108`

```python
# sinput = static input, not optimizable
optimizable = (input_type == 'input') and (base_type in ['int', 'double'])

# Injected safety params must never be optimized
if name.startswith('EAStressSafety_'):
    optimizable = False
```

### Gate Function

`engine/gates.py:77-90`

```python
def check_params_found(params: list) -> GateResult:
    """Gate 3: Check if parameters were extracted."""
    count = len(params) if params else 0
    optimizable = sum(1 for p in params if p.get('optimizable', False)) if params else 0
    passed = count > 0

    return GateResult(
        name='params_found',
        passed=passed,
        value=count,
        threshold=1,
        operator='>=',
        message=f"{'PASS' if passed else 'FAIL'}: Found {count} parameters ({optimizable} optimizable)"
    )
```

**Edge cases:**
- Commented-out inputs are skipped
- Enum types detected by `ENUM_` prefix or all-uppercase name
- Default values include quotes for strings (e.g., `'"MyEA"'`)
- Multi-line input declarations not supported (must be single line)

**Known issues:** None.

## Skill Integration

**After this step:** Workflow pauses in `awaiting_param_analysis` state.

The `/param-analyzer` skill is invoked to:
1. Read the extracted params
2. Understand each parameter's purpose from EA source code
3. Generate `wide_validation_params` (maximize trades for Step 5)
4. Generate `optimization_ranges` (ranges for genetic optimization)

The skill calls `runner.continue_with_params(wide_params, opt_ranges)` to resume.

**Contract for skill output:**

```python
# wide_validation_params: Dict[str, value]
{
    'Lots': 0.1,
    'StopLoss': 100,
    'TakeProfit': 200,
    # ... one value per param to maximize trading
}

# optimization_ranges: List[dict]
[
    {
        'name': 'Lots',
        'start': 0.01,
        'stop': 1.0,
        'step': 0.01,
        'optimize': True,
        'category': 'risk',
        'rationale': 'Standard lot range for testing'
    },
    {
        'name': 'MagicNumber',
        'start': 12345,
        'stop': 12345,
        'step': 0,
        'optimize': False,
        'category': 'identifier',
        'rationale': 'Fixed identifier, no optimization needed'
    }
]
```
