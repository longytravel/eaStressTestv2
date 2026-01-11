# Step 1: Load EA

## Overview

Verifies that the EA source file exists before proceeding with the workflow.

This is the entry gate - if the file doesn't exist, the workflow cannot proceed.

## Inputs

| Name | Type | Source | Description |
|------|------|--------|-------------|
| `ea_path` | `str` | `WorkflowRunner.__init__()` | Absolute path to `.mq5` file |

## Outputs

| Name | Type | Destination | Description |
|------|------|-------------|-------------|
| `path` | `str` | Step result | Validated path string |
| `exists` | `bool` | Step result | Whether file exists |
| `gate` | `dict` | Step result, `state.gates` | Gate result object |

**Result structure:**
```python
{
    'path': '/path/to/EA.mq5',
    'exists': True,
    'gate': {
        'name': 'file_exists',
        'passed': True,
        'value': 1,
        'threshold': 1,
        'operator': '==',
        'message': 'PASS: EA file exists: /path/to/EA.mq5'
    }
}
```

## Gate

| Gate Name | Condition | Threshold | Operator |
|-----------|-----------|-----------|----------|
| `file_exists` | `Path(path).exists()` | `1` (file exists) | `==` |

**Pass condition:** File exists at specified path.

**Fail condition:** File not found.

## Implementation Notes

**Source:** `engine/runner.py:1443-1451`

```python
def _step_load_ea(self) -> tuple[bool, dict]:
    """Step 1: Verify EA file exists."""
    gate = gates.check_file_exists(str(self.ea_path))
    return gate.passed, {
        'path': str(self.ea_path),
        'exists': gate.passed,
        'gate': gate.to_dict(),
    }
```

**Gate function:** `engine/gates.py:50-60`

```python
def check_file_exists(path: str) -> GateResult:
    """Gate 1: Check if EA file exists."""
    exists = Path(path).exists()
    return GateResult(
        name='file_exists',
        passed=exists,
        value=1 if exists else 0,
        threshold=1,
        operator='==',
        message=f"{'PASS' if exists else 'FAIL'}: EA file {'exists' if exists else 'not found'}: {path}"
    )
```

**Edge cases:**
- Path must be absolute (relative paths may work but are not guaranteed)
- File must be readable (permissions not explicitly checked)
- File extension not validated (could be `.mq4` or other)

**Known issues:** None.

## Skill Integration

None. This step is fully automated.
