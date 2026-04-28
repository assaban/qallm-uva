import pytest
from pathlib import Path
from qallm.ingestion.parsers import CodeUnit
from qallm.analysis.metrics import StaticAnalyzer


@pytest.fixture
def vulnerable_code_unit():
    """Provides a code unit with high complexity and a security flaw."""
    code = """
def process_data(user_input):
    password = "fixed_password_123"  # Bandit B105
    for i in range(10):
        for j in range(10):
            for k in range(10):
                print(i, j, k)
    return True
"""
    return CodeUnit(source=code, cell_index=1, original_path=Path("test.ipynb"))


def test_static_analyzer_complexity(vulnerable_code_unit):
    """Verifies that Radon metrics (MI and CC) are captured."""
    analyzer = StaticAnalyzer()
    report = analyzer._analyze_single_unit(vulnerable_code_unit)

    # Check Maintainability Index
    assert "mi" in report["metrics"]
    assert isinstance(report["metrics"]["mi"], (int, float))

    # Check Cyclomatic Complexity
    assert "cc" in report["metrics"]
    assert report["metrics"]["cc"] > 1


def test_static_analyzer_security(vulnerable_code_unit):
    """Verifies that Bandit security issues are captured[cite: 608, 632]."""
    analyzer = StaticAnalyzer()
    report = analyzer._analyze_single_unit(vulnerable_code_unit)

    assert len(report["issues"]) > 0
    issue_ids = [issue["test_id"] for issue in report["issues"]]
    assert "B105" in issue_ids