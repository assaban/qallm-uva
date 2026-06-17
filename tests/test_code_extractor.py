"""Tests for CodeExtractor: validates that LLM chatter is stripped and valid Python is extracted."""
from qallm.verification.extraction import CodeExtractor


class TestMarkdownExtraction:
    """Strategy 1 & 2: extracting from markdown code blocks."""

    def test_python_block_extracted(self):
        raw = """Here is a test for you:

```python
import pytest

def test_add():
    assert 1 + 1 == 2
```

I hope this helps!"""
        code, strategy = CodeExtractor.extract(raw)
        assert strategy == "markdown_python_block"
        assert "def test_add" in code
        assert "I hope this helps" not in code

    def test_generic_block_extracted(self):
        raw = """Sure, here you go:

```
import pytest

def test_subtract():
    assert 5 - 3 == 2
```
"""
        code, strategy = CodeExtractor.extract(raw)
        assert strategy == "markdown_generic_block"
        assert "def test_subtract" in code
        assert "Sure" not in code

    def test_multiple_python_blocks_merged(self):
        raw = """```python
import pytest
```

Some explanation...

```python
def test_a():
    assert True
```"""
        code, strategy = CodeExtractor.extract(raw)
        assert "import pytest" in code
        assert "def test_a" in code


class TestDialogueFiltering:
    """Strategy 3: filtering out conversational lines."""

    def test_dialogue_stripped(self):
        raw = """I understand you want tests. Here is a comprehensive test suite.
Based on the code analysis, the following tests target edge cases.
import pytest

def test_edge():
    assert [] == []
"""
        code, strategy = CodeExtractor.extract(raw)
        assert "def test_edge" in code
        assert "I understand" not in code

    def test_pure_code_passes_through(self):
        raw = """import pytest

def test_simple():
    assert 42 == 42
"""
        code, strategy = CodeExtractor.extract(raw)
        assert "def test_simple" in code
        # Should be extracted via raw_text or dialogue_filter
        assert strategy in ("dialogue_filter", "raw_text")


class TestASTValidation:
    """Core P0 fix: AST validation catches broken code."""

    def test_broken_syntax_triggers_fallback(self):
        raw = "def test_broken(: assert True"  # missing close paren
        code, strategy = CodeExtractor.extract(raw)
        # Should fall through to fallback
        assert "fallback" in strategy or "function_defs" in strategy

    def test_broken_imports_stripped(self):
        raw = """```python
import pytest
from some.weird..path import thing

def test_ok():
    assert True
```"""
        code, strategy = CodeExtractor.extract(raw)
        # Should still extract valid code after stripping the bad import
        assert "def test_ok" in code
        assert "import_cleanup" in strategy or "STRIPPED" in code or strategy == "markdown_python_block"

    def test_empty_response_returns_fallback(self):
        code, strategy = CodeExtractor.extract("")
        assert strategy == "fallback"
        assert "def test_" in code


class TestFunctionDefExtraction:
    """Strategy 5: nuclear option, extract only test function definitions."""

    def test_extracts_test_functions_from_mixed_text(self):
        raw = """This is a comprehensive test suite for the pipeline module.
We test edge cases and error handling.

def test_empty_input():
    result = process([])
    assert result is None

Some more explanation about the next test.

def test_negative_values():
    result = process([-1, -2])
    assert len(result) == 2
"""
        code, strategy = CodeExtractor.extract(raw)
        assert "def test_empty_input" in code
        assert "def test_negative_values" in code


class TestRealWorldLLMOutputs:
    """Test with patterns actually observed from Gemma and GPT outputs."""

    def test_gemma_style_chatter(self):
        raw = """## Test Cases for pipeline.py

I'll generate comprehensive tests targeting the identified functions.

```python
import pytest

def test_run_pipeline_csv():
    \"\"\"Test CSV loading path.\"\"\"
    result = run_pipeline("data.csv", "target")
    assert result is not None

def test_run_pipeline_unsupported():
    \"\"\"Test unsupported file format.\"\"\"
    result = run_pipeline("data.xlsx", "target")
    assert result is None
```

These tests cover the main execution paths and verify error handling for edge cases.
"""
        code, strategy = CodeExtractor.extract(raw)
        assert strategy == "markdown_python_block"
        assert "def test_run_pipeline_csv" in code
        assert "def test_run_pipeline_unsupported" in code
        assert "## Test Cases" not in code
        assert "These tests cover" not in code
