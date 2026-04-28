"""Tests for DependencyMapper: validates sibling module copying and import sanitization."""
import pytest
import tempfile
from pathlib import Path
from qallm.verification.sandbox import DependencyMapper


class TestResolveAndCopy:
    """Test that sibling files and packages are correctly copied to the sandbox."""

    def test_copies_sibling_py_files(self, tmp_path):
        # Create a project directory with two .py files
        project = tmp_path / "project"
        project.mkdir()
        target = project / "main.py"
        target.write_text("from sibling import helper\n")
        sibling = project / "sibling.py"
        sibling.write_text("def helper(): return 42\n")

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        copied = DependencyMapper.resolve_and_copy(target, sandbox)
        assert "sibling" in copied
        assert (sandbox / "sibling.py").exists()

    def test_copies_package_when_init_exists(self, tmp_path):
        # Create a package structure
        pkg = tmp_path / "my_package"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "config.py").write_text("X = 1\n")
        (pkg / "utils.py").write_text("def foo(): pass\n")
        target = pkg / "main.py"
        target.write_text("from my_package.config import X\n")

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        copied = DependencyMapper.resolve_and_copy(target, sandbox)
        assert "my_package" in copied
        assert (sandbox / "my_package" / "__init__.py").exists()
        assert (sandbox / "my_package" / "config.py").exists()

    def test_handles_nonexistent_parent_gracefully(self, tmp_path):
        fake_path = tmp_path / "nonexistent" / "file.py"
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        copied = DependencyMapper.resolve_and_copy(fake_path, sandbox)
        assert copied == []

    def test_does_not_copy_target_itself(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        target = project / "main.py"
        target.write_text("x = 1\n")
        other = project / "other.py"
        other.write_text("y = 2\n")

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        copied = DependencyMapper.resolve_and_copy(target, sandbox)
        assert "main" not in copied
        assert "other" in copied
