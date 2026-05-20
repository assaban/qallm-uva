import pytest
from pathlib import Path
from qallm.common.model import CodeUnit
from qallm.analysis.analysis_manager import AnalysisManager


@pytest.fixture
def vulnerable_code_unit():
    """Provides a code unit with high complexity and a security flaw[cite: 15]."""
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
    """Verifies that AnalysisManager returns an AnalysedCodeUnit with findings."""
    manager = AnalysisManager()
    # Ported: Use analyse_code_unit for single units
    analysed = manager.analyse_code_unit(vulnerable_code_unit)

    assert hasattr(analysed, "findings"), "Result should be an AnalysedCodeUnit with findings"
    assert isinstance(analysed.findings, list)
    assert len(analysed.findings) > 0


def test_analysis_manager_detects_security_issues(vulnerable_code_unit):
    """Verifies that Bandit security issues are captured[cite: 15]."""
    manager = AnalysisManager()
    # Ported: Access findings attribute from the returned AnalysedCodeUnit[cite: 11]
    analysed = manager.analyse_code_unit(vulnerable_code_unit)
    findings = analysed.findings

    security_findings = [f for f in findings if f.tool == "bandit"]
    assert len(security_findings) > 0
    rule_ids = [f.rule_id for f in security_findings]
    assert "B105" in rule_ids


def test_analysis_manager_detects_complexity(vulnerable_code_unit):
    """Verifies that Radon complexity analysis runs without error."""
    # manager = AnalysisManager(selected_tools=["radon"])
    manager = AnalysisManager()
    # Ported: Use the unit-based analysis method[cite: 11]
    analysed = manager.analyse_code_unit(vulnerable_code_unit)

    assert isinstance(analysed.findings, list)

    # FIX: Check if Radon is present in the raw results list by inspecting object attributes
    radon_ran = any(r.tool.lower() == "radon" for r in analysed.raw_tool_results)

    # Also check if it produced a finding (only happens if thresholds CC > 5 or MI < 70 are met)[cite: 15]
    radon_finding = "radon" in [f.tool for f in analysed.findings]

    assert radon_ran or radon_finding