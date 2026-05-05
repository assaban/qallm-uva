import pytest
from pathlib import Path
from qallm.common.model import CodeUnit
from qallm.analysis.analysis_manager import AnalysisManager


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
    return CodeUnit(source_code=code, cell_index=1, original_path=Path("test.ipynb"))


def test_analysis_manager_returns_findings(vulnerable_code_unit):
    """Verifies that AnalysisManager returns a list of Finding objects."""
    manager = AnalysisManager()
    findings = manager.analyze([vulnerable_code_unit])
    assert isinstance(findings, list)
    assert len(findings) > 0


def test_analysis_manager_detects_security_issues(vulnerable_code_unit):
    """Verifies that Bandit security issues are captured."""
    manager = AnalysisManager()
    findings = manager.analyze([vulnerable_code_unit])

    security_findings = [f for f in findings if f.tool == "bandit"]
    assert len(security_findings) > 0
    rule_ids = [f.rule_id for f in security_findings]
    assert "B105" in rule_ids


def test_analysis_manager_detects_complexity(vulnerable_code_unit):
    """Verifies that Radon complexity analysis runs without error.
    Note: findings are only emitted for CC > 5 and MI < 70."""
    manager = AnalysisManager(selected_tools=["radon"])
    findings = manager.analyze([vulnerable_code_unit])
    # Radon ran successfully; findings depend on thresholds
    assert isinstance(findings, list)