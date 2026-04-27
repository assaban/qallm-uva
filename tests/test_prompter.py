import pytest
from qallm.stage2_lre.prompter import PromptConstructor, EvidenceBundle


@pytest.fixture
def prompter():
    return PromptConstructor()


def test_prompt_contains_source_and_metrics(prompter):
    """Verifies that the prompt includes core code and structural metrics."""
    bundle = EvidenceBundle(
        source_code="def add(a, b): return a + b",
        cell_index=0,
        metrics={"mi": 100.0, "cc": 1.0},
        static_issues=[],
        lifecycle_status="PUBLICATION"
    )
    prompt = prompter.build_verification_prompt(bundle)

    assert "def add(a, b)" in prompt
    assert "Maintainability Index: 100.0" in prompt
    assert "Lifecycle Status: PUBLICATION" in prompt
    assert "None" in prompt  # For identified issues


def test_prompt_formats_multiple_issues(prompter):
    """Verifies that multiple security findings are correctly injected into the context."""
    bundle = EvidenceBundle(
        source_code="password = '123'\nexec(user_input)",
        cell_index=5,
        metrics={"mi": 50.0, "cc": 4.0},
        static_issues=[
            {"test_id": "B105", "issue_text": "Hardcoded password"},
            {"test_id": "B102", "issue_text": "Use of exec detected"}
        ],
        lifecycle_status="IMPLEMENTATION"
    )
    prompt = prompter.build_verification_prompt(bundle)

    # Check that both Bandit IDs and their descriptions are present
    assert "B105: Hardcoded password" in prompt
    assert "B102: Use of exec detected" in prompt
    assert "Cell 5" in prompt


def test_system_prompt_requirements(prompter):
    """Ensures the system prompt aligns with our oracle research goals."""
    system_msg = prompter.SYSTEM_PROMPT
    assert "Crash" in system_msg
    assert "Property" in system_msg
    assert "Metamorphic" in system_msg