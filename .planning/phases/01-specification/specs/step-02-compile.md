# Step 2: Compile

## Overview

Compiles the modified EA using MetaEditor64, producing an executable `.ex5` file.

This is the first gate where the EA can fail due to code errors. If compilation fails, the `/mql5-fixer` skill is invoked to diagnose and repair.

## Inputs

| Name | Type | Source | Description |
|------|------|--------|-------------|
| `ea_path` | `str` | `runner.modified_ea_path` or `runner.ea_path` | Path to `.mq5` file |
| `terminal` | `dict` | `runner.terminal` | Terminal config (contains MetaEditor path) |
| `include_path` | `str` | Optional | Custom include path (rarely used) |

## Outputs

| Name | Type | Destination | Description |
|------|------|-------------|-------------|
| `success` | `bool` | Step result | Whether compilation succeeded |
| `exe_path` | `str` | Step result, `runner.compiled_ea_path` | Path to `.ex5` if successful |
| `errors` | `list[str]` | Step result | Compilation errors |
| `warnings` | `list[str]` | Step result | Compilation warnings |
| `output` | `str` | Step result | Raw compiler output + log content |
| `gate` | `dict` | Step result, `state.gates` | Gate result object |

**Result structure:**
```python
{
    'success': True,
    'exe_path': '/path/to/EA_stress_test.ex5',
    'errors': [],
    'warnings': ['some warning about unused variable'],
    'output': '... compiler output ...',
    'gate': {
        'name': 'compilation',
        'passed': True,
        'value': 0,
        'threshold': 0,
        'operator': '==',
        'message': 'PASS: Compilation succeeded'
    }
}
```

## Gate

| Gate Name | Condition | Threshold | Operator |
|-----------|-----------|-----------|----------|
| `compilation` | Error count | `0` | `==` |

**Pass condition:** `.ex5` file created AND zero errors.

**Fail condition:**
- MetaEditor64 not found
- Compilation errors (syntax, missing includes, type errors)
- `.ex5` file not created
- Timeout (60 seconds)

## Implementation Notes

**Source:** `engine/runner.py:1479-1491`

```python
def _step_compile(self) -> tuple[bool, dict]:
    """Step 2: Compile the EA."""
    ea_to_compile = self.modified_ea_path or str(self.ea_path)

    result = compile_ea(ea_to_compile, terminal=self.terminal)
    gate = gates.check_compilation(result)

    if result['success']:
        self.compiled_ea_path = result['exe_path']

    self.state.update_gates({'compilation': gate.to_dict()})
    return gate.passed, {**result, 'gate': gate.to_dict()}
```

**Compiler module:** `modules/compiler.py:16-153`

### Compilation Process

1. **Find MetaEditor64:** `modules/compiler.py:56-67`
   ```python
   terminal_path = Path(terminal['path'])
   metaeditor_path = terminal_path.parent / 'MetaEditor64.exe'
   ```

2. **Build command:** `modules/compiler.py:69-80`
   ```python
   cmd = [
       str(metaeditor_path),
       f'/compile:{ea_path}',
       '/log',
   ]
   if include_path:
       cmd.append(f'/inc:{include_path}')
   ```

3. **Run subprocess:** `modules/compiler.py:82-107`
   - Working directory: EA's parent folder
   - Timeout: 60 seconds
   - Captures stdout + stderr

4. **Parse log file:** `modules/compiler.py:109-136`
   - Log path: `{ea_path}.log` (same name, `.log` extension)
   - Encodings tried: UTF-16-LE, then UTF-8
   - Error pattern: ` : error ` or `: error `
   - Warning pattern: ` : warning ` or `: warning `

5. **Verify output:** `modules/compiler.py:138-145`
   - Success = `.ex5` exists AND zero errors

### Gate Function

`engine/gates.py:63-74`

```python
def check_compilation(compile_result: dict) -> GateResult:
    """Gate 2: Check if compilation succeeded."""
    success = compile_result.get('success', False)
    errors = len(compile_result.get('errors', []))
    return GateResult(
        name='compilation',
        passed=success,
        value=0 if success else errors,
        threshold=0,
        operator='==',
        message=f"{'PASS' if success else 'FAIL'}: Compilation {'succeeded' if success else f'failed with {errors} error(s)'}"
    )
```

**Edge cases:**
- MetaEditor finds includes automatically when EA is in terminal's Experts folder
- Log file encoding varies by Windows locale
- Warnings don't fail compilation

**Known issues:** None.

## Skill Integration

**On failure:** `/mql5-fixer` skill is invoked to diagnose compilation errors.

The skill receives:
- Compilation errors from `result['errors']`
- Raw output from `result['output']`
- Path to source file

The skill:
1. Analyzes error messages
2. Reads relevant source code
3. Proposes fixes
4. User approves, then step is re-run
