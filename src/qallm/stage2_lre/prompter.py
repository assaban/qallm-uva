from dataclasses import dataclass
from typing import Dict, Any, List


@dataclass
class EvidenceBundle:
    """Combines code with static diagnostics for LLM context."""
    source_code: str
    cell_index: int
    metrics: Dict[str, Any]
    static_issues: List[Dict[str, Any]]
    lifecycle_status: str
    file_name: str  # Fixed the missing attribute


class PromptConstructor:
    """Generates targeted prompts for the Test Case Agent."""

    SYSTEM_PROMPT = (
        "You are an expert Software Test Engineer. Your goal is to generate "
        "Python test cases using pytest. Focus on finding bugs via Crash, "
        "Property, and Metamorphic oracles. Ensure you target specific "
        "functions and classes present in the code."
    )

    def build_verification_prompt(self, bundle: EvidenceBundle, signatures: List[str]) -> str:
        """Constructs a context-rich prompt for the LLM."""
        issues_formatted = self._format_issues_by_tool(bundle.static_issues)

        prompt = f"""
### Target File: {bundle.file_name} (Cell {bundle.cell_index})
### Code Inventory (Found Signatures): {", ".join(signatures) if signatures else "Constants/Global code only"}

### Target Code:
```python
{bundle.source_code}
        Static Analysis Findings:
        {issues_formatted}
        
        Instructions:
        1. Generate pytest cases for the functions/classes listed in the inventory.
        2. If only constants are present, verify their values and types.
        3. Address specific static analysis warnings (e.g., security risks) in your test cases.
        4. DO NOT include the original code or imports of the target file; it is \
        already available in the test environment.
        """
        return prompt

    def _format_issues_by_tool(self, issues: List[Dict[str, Any]]) -> str:
        if not issues:
            return "✅ Static Analysis (Bandit/Radon): No specific issues identified."

        lines = ["⚠️ Identified Static Issues:"]
        for i in issues:
            # Determine tool based on the 'test_id' (Bandit uses BXXX)
            tool = "Bandit (Security)" if str(i.get('test_id', '')).startswith('B') else "Radon (Structural)"
            lines.append(f"- [{tool}] {i.get('test_id')}: {i.get('issue_text')}")
        return "\n".join(lines)