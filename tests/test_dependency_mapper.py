"""Tests for DependencyMapper: validates sibling module copying and import sanitization."""
from qallm.verification.extraction import DependencyMapper


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


class TestNamespacePackageFallback:
    """When the upload has no __init__.py, the package-root walk fails.
    The AST-scan secondary pass should still resolve top-level imports
    by matching directory names.
    """

    def test_namespace_package_resolved_via_ast(self, tmp_path):
        # Layout:
        #   project/
        #     pipeline.py        <- target; imports from research_pipeline.config
        #     research_pipeline/ <- no __init__.py (namespace package)
        #       config.py
        project = tmp_path / "project"
        (project / "research_pipeline").mkdir(parents=True)
        target = project / "pipeline.py"
        target.write_text(
            "from research_pipeline.config import THRESHOLD\n"
            "def go(): return THRESHOLD\n",
            encoding="utf-8",
        )
        (project / "research_pipeline" / "config.py").write_text(
            "THRESHOLD = 0.5\n", encoding="utf-8",
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        copied = DependencyMapper.resolve_and_copy(target, sandbox)
        assert "research_pipeline" in copied
        assert (sandbox / "research_pipeline" / "config.py").exists()

    def test_does_not_copy_stdlib_names(self, tmp_path):
        # 'os' and 'json' are imported but should not match anything on disk;
        # the AST-scan pass must silently skip them.
        project = tmp_path / "project"
        project.mkdir()
        target = project / "main.py"
        target.write_text(
            "import os\nimport json\ndef go(): return os.getcwd()\n",
            encoding="utf-8",
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        copied = DependencyMapper.resolve_and_copy(target, sandbox)
        # No siblings, no on-disk packages matching imports.
        assert "os" not in copied
        assert "json" not in copied

    def test_search_walks_up_a_few_levels(self, tmp_path):
        # Layout:
        #   project/
        #     myhelpers/
        #       config.py
        #     subdir/
        #       script.py   <- target; imports myhelpers
        # script.py's parent doesn't contain myhelpers, but script.py's
        # grandparent does. The search should walk up to find it.
        project = tmp_path / "project"
        (project / "myhelpers").mkdir(parents=True)
        (project / "subdir").mkdir()
        target = project / "subdir" / "script.py"
        target.write_text(
            "from myhelpers.config import X\n", encoding="utf-8",
        )
        (project / "myhelpers" / "config.py").write_text(
            "X = 42\n", encoding="utf-8",
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        copied = DependencyMapper.resolve_and_copy(target, sandbox)
        assert "myhelpers" in copied
        assert (sandbox / "myhelpers" / "config.py").exists()

    def test_warns_when_nothing_copied(self, tmp_path, caplog):
        # Bare script with no siblings, no imports that match anything.
        project = tmp_path / "project"
        project.mkdir()
        target = project / "loner.py"
        target.write_text("def f(): pass\n", encoding="utf-8")

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        import logging
        with caplog.at_level(logging.WARNING):
            DependencyMapper.resolve_and_copy(target, sandbox)

        # The warning is expected and helps the user diagnose missing imports.
        assert any("nothing copied" in r.message.lower()
                   for r in caplog.records)
