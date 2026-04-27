from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class EvidenceBundle:
    """Combines code with static diagnostics for LLM context[cite: 215]."""
    source_code: str
    cell_index: int
    metrics: Dict[str, Any]
    static_issues: List[Dict[str, Any]]
    lifecycle_status: str

class PromptConstructor:
    """Generates targeted prompts for the Test Case Agent[cite: 271]."""

    SYSTEM_PROMPT = (
        "You are an expert Software Test Engineer. Your goal is to generate "
        "Python test cases using pytest that detect bugs via Crash, Property, "
        "and Metamorphic oracles[cite: 223, 225, 228]."
    )

    def build_verification_prompt(self, bundle: EvidenceBundle) -> str:
        """Constructs a prompt bundling code and static warnings[cite: 70]."""
        prompt = f"""
            ### Target Code (Cell {bundle.cell_index}):
            ```python
            {bundle.source_code}
            Static Analysis Context:
            Maintainability Index: {bundle.metrics.get('mi', 'N/A')}
    
            Cyclomatic Complexity: {bundle.metrics.get('cc', 'N/A')}
    
            Lifecycle Status: {bundle.lifecycle_status}
    
            Identified Issues: {self._format_issues(bundle.static_issues)}
    
            Instructions:
            Generate a pytest suite that maximizes branch coverage and targets the
            identified static issues. Use property-based testing concepts if applicable.
            """
        return prompt

    def _format_issues(self, issues: List[Dict[str, Any]]) -> str:
        if not issues:
            return "None"
        return ", ".join([f"{i.get('test_id')}: {i.get('issue_text')}" for i in issues])