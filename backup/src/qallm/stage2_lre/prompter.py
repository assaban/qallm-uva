from dataclasses import dataclass
from pathlib import Path
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
        "You are a Python test generation engine. You output ONLY executable Python code. "
        "NEVER include explanations, markdown headers, or conversational text outside of "
        "a single ```python code block. Your output must be directly executable by pytest. "
        "Focus on finding bugs via three oracle types: Crash (edge-case inputs that trigger "
        "exceptions), Property (output invariants from docstrings/type hints), and "
        "Metamorphic (consistent relationships between related inputs). "
        "Target specific functions and classes present in the provided code."
    )

    def build_verification_prompt(self, bundle: EvidenceBundle, signatures: List[str]) -> str:
        """Constructs a context-rich prompt for the LLM."""
        issues_formatted = self._format_issues_by_tool(bundle.static_issues)

        # Build the import hint: tell the LLM the exact module name to import from
        src_stem = Path(bundle.file_name).stem
        import_hint = f"from {src_stem} import *"

        prompt = f"""### Target File: {bundle.file_name} (Cell {bundle.cell_index})
### Code Inventory (Found Signatures): {", ".join(signatures) if signatures else "Constants/Global code only"}

### Target Code:
```python
{bundle.source_code}
```

### Static Analysis Findings:
{issues_formatted}

### Test Environment:
The target code is importable as: `{import_hint}`
All dependencies of the target file are pre-installed in the sandbox.

### INSTRUCTIONS (FOLLOW EXACTLY):
1. Output ONLY a single Python code block. No explanation, no markdown outside the block.
2. Start with `import pytest` then `{import_hint}`.
3. Generate pytest test functions for the signatures listed above.
4. Use three oracle types where applicable:
   a. Crash oracle: call functions with edge-case inputs (empty list, None, zero).
   b. Property oracle: assert output invariants derivable from docstrings/type hints.
   c. Metamorphic oracle: assert consistent relationships between related inputs.
5. If only constants are present, verify their values and types.
6. Target specific static analysis warnings (e.g., security risks) in your tests.
7. Do NOT redefine the target functions. Do NOT import from the original project path.
8. Every test function name must start with `test_`.

### OUTPUT FORMAT:
```python
import pytest
{import_hint}

def test_...:
    ...
```"""
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