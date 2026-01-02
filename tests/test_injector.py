"""
Tests for EA Code Injector

Tests OnTester injection and safety guards.
"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from modules.injector import (
    has_ontester,
    has_safety_guards,
    inject_ontester,
    inject_safety,
    create_modified_ea,
    restore_original,
)


class TestHasOntester:
    """Tests for OnTester detection."""

    def test_detect_ontester_double(self):
        """Test detecting double OnTester."""
        code = '''
double OnTester()
{
    return 1.0;
}
'''
        assert has_ontester(code) == True

    def test_detect_ontester_int(self):
        """Test detecting int OnTester."""
        code = '''
int OnTester()
{
    return 1;
}
'''
        assert has_ontester(code) == True

    def test_no_ontester(self, sample_ea_code):
        """Test no OnTester in sample EA."""
        assert has_ontester(sample_ea_code) == False

    def test_ontester_in_comment(self):
        """Test OnTester in comment is not detected."""
        code = '''
// double OnTester() { return 1.0; }
/* OnTester function would go here */
'''
        assert has_ontester(code) == False


class TestHasSafetyGuards:
    """Tests for safety guard detection."""

    def test_detect_safety(self):
        """Test detecting STRESS_TEST_MODE."""
        code = '''
#define STRESS_TEST_MODE true
'''
        assert has_safety_guards(code) == True

    def test_no_safety(self, sample_ea_code):
        """Test no safety guards in sample EA."""
        assert has_safety_guards(sample_ea_code) == False


class TestInjectOntester:
    """Tests for OnTester injection."""

    def test_inject_ontester(self, sample_ea_code):
        """Test OnTester is injected."""
        modified, was_injected = inject_ontester(sample_ea_code)

        assert was_injected == True
        assert has_ontester(modified) == True
        assert 'OnTester' in modified
        assert 'TesterStatistics' in modified

    def test_no_double_inject(self, sample_ea_code):
        """Test OnTester not injected twice."""
        modified1, _ = inject_ontester(sample_ea_code)
        modified2, was_injected = inject_ontester(modified1)

        assert was_injected == False
        assert modified1 == modified2

    def test_inject_preserves_code(self, sample_ea_code):
        """Test original code is preserved."""
        modified, _ = inject_ontester(sample_ea_code)

        # Original functions should still be there
        assert 'OnInit' in modified
        assert 'OnDeinit' in modified
        assert 'OnTick' in modified
        assert 'input int      Period' in modified


class TestInjectSafety:
    """Tests for safety guard injection."""

    def test_inject_safety(self, sample_ea_code):
        """Test safety guards are injected."""
        modified, was_injected = inject_safety(sample_ea_code)

        assert was_injected == True
        assert has_safety_guards(modified) == True
        assert 'STRESS_TEST_MODE' in modified

    def test_safety_includes_protections(self, sample_ea_code):
        """Test specific safety macros are included."""
        modified, _ = inject_safety(sample_ea_code)

        assert 'FileOpen' in modified
        assert 'WebRequest' in modified
        assert 'INVALID_HANDLE' in modified

    def test_no_double_inject_safety(self, sample_ea_code):
        """Test safety not injected twice."""
        modified1, _ = inject_safety(sample_ea_code)
        modified2, was_injected = inject_safety(modified1)

        assert was_injected == False
        assert modified1 == modified2


class TestCreateModifiedEA:
    """Tests for creating modified EA files."""

    def test_create_modified_ea(self, sample_ea_file, temp_dir):
        """Test creating modified EA copy."""
        result = create_modified_ea(str(sample_ea_file))

        assert result['success'] == True
        assert result['original_path'] == str(sample_ea_file)
        assert result['modified_path'] is not None
        assert '_stress_test' in result['modified_path']

        # Verify file was created
        modified_path = Path(result['modified_path'])
        assert modified_path.exists()

        # Verify content has injections
        content = modified_path.read_text()
        assert has_ontester(content)
        assert has_safety_guards(content)

    def test_create_with_custom_suffix(self, sample_ea_file, temp_dir):
        """Test custom suffix."""
        result = create_modified_ea(str(sample_ea_file), suffix='_test_v2')

        assert '_test_v2' in result['modified_path']

    def test_create_in_custom_dir(self, sample_ea_file, temp_dir):
        """Test creating in custom directory."""
        output_dir = temp_dir / "output"
        result = create_modified_ea(str(sample_ea_file), output_dir=str(output_dir))

        assert result['success'] == True
        assert str(output_dir) in result['modified_path']
        assert (output_dir / "TestEA_stress_test.mq5").exists()

    def test_skip_ontester_injection(self, sample_ea_file):
        """Test skipping OnTester injection."""
        result = create_modified_ea(str(sample_ea_file), inject_tester=False)

        assert result['success'] == True
        assert result['ontester_injected'] == False

        content = Path(result['modified_path']).read_text()
        assert not has_ontester(content)

    def test_skip_safety_injection(self, sample_ea_file):
        """Test skipping safety injection."""
        result = create_modified_ea(str(sample_ea_file), inject_guards=False)

        assert result['success'] == True
        assert result['safety_injected'] == False

        content = Path(result['modified_path']).read_text()
        assert not has_safety_guards(content)

    def test_file_not_found(self, temp_dir):
        """Test error when file not found."""
        result = create_modified_ea(str(temp_dir / "nonexistent.mq5"))

        assert result['success'] == False
        assert 'not found' in result['errors'][0].lower()


class TestRestoreOriginal:
    """Tests for cleanup of modified EAs."""

    def test_restore_deletes_modified(self, sample_ea_file, temp_dir):
        """Test restore deletes modified file."""
        result = create_modified_ea(str(sample_ea_file))
        modified_path = result['modified_path']

        assert Path(modified_path).exists()

        deleted = restore_original(modified_path)

        assert deleted == True
        assert not Path(modified_path).exists()

    def test_restore_deletes_ex5(self, sample_ea_file, temp_dir):
        """Test restore also deletes .ex5 file."""
        result = create_modified_ea(str(sample_ea_file))
        modified_path = result['modified_path']

        # Create fake .ex5 file
        ex5_path = Path(modified_path).with_suffix('.ex5')
        ex5_path.touch()

        deleted = restore_original(modified_path)

        assert deleted == True
        assert not ex5_path.exists()

    def test_restore_safe_check(self, sample_ea_file):
        """Test restore won't delete non-stress-test files."""
        # Try to delete original (no _stress_test suffix)
        deleted = restore_original(str(sample_ea_file))

        assert deleted == False
        assert sample_ea_file.exists()
