"""LLM-based repair agent with compile validation and self-correction retry.

Flow per file:
  1. Build prompt from findings + source
  2. Call LLM, strip markdown fences
  3. Validate with ast.parse()
  4. If invalid: feed SyntaxError back to LLM, retry once
  5. Return RepairResult with compile status
"""

import re

from qallm.llm.base import LLMModel, TokenTracker
from qallm.repair.repair_model import RepairResult, RepairRequest, RepairAgent

BT = chr(96) * 3

SYSTEM_PROMPT = """
You are a senior Python security and quality engineer.
Fix the code to address ALL the provided issues with minimal changes. Issues
come in two kinds: static analysis findings, and runtime verification failures
(a generated test that failed when run against the code, evidence of a logical
flaw that static analysis did not catch). Fix both kinds.

Rules:
1. Preserve external behavior unless a finding requires changing it for safety.
2. Do not introduce new dependencies unless explicitly allowed.
3. Prefer safe standard-library alternatives (e.g. ast.literal_eval over eval,
   subprocess with list args over shell=True).
4. Remove hardcoded secrets and replace with os.environ reads (never print secrets).
5. If a finding is a false positive or cannot be fixed safely, keep the
   original code unchanged and add a # noqa comment on the relevant line.
6. Keep changes small and localized, fix only the reported issues.
7. For a runtime failure, make the function behave correctly so the failing
   test would pass; do not edit the test, fix the code under test.
8. Return the COMPLETE corrected file. No explanations, no markdown fences,
   no partial snippets. Return the full file from first line to last line.
9. Ensure all imports needed by your fixes are present at the top of the file.
"""

MAX_RETRIES = 1


class LLMRepairAgent(RepairAgent):
    """Concrete RepairAgent with compile validation and self-correction retry."""

    def __init__(self, llm: LLMModel, tracker: TokenTracker | None = None):
        self.llm = llm
        self.tracker = tracker or TokenTracker(budget=50_000)

    def repair(self, request: RepairRequest) -> RepairResult:
        """Invoke LLM to repair a file. Retries once on SyntaxError."""
        findings_text = "\n".join([
            f"  [{f.severity}] {f.rule_id} (line {f.line}): {f.message}"
            for f in request.current_findings
        ]) or "  (none)"

        # Runtime verification failures: a logical flaw with no static finding.
        # Include the failing test so the agent can see the expected behaviour.
        runtime_text = ""
        if request.verification_failures:
            blocks = []
            for vf in request.verification_failures:
                excerpt = (vf.error_excerpt or "").strip()
                blocks.append(
                    f"  Function `{vf.function_name}` fails this test:\n"
                    f"{vf.failing_test}\n"
                    + (f"  Error: {excerpt}\n" if excerpt else "")
                )
            runtime_text = (
                "\n\nRuntime verification failures (logical flaws found by "
                "execution, no static finding). Fix the function so the test "
                "passes:\n" + "\n".join(blocks)
            )

        user_prompt = f"""File: {request.file_path}

Findings to fix:
{findings_text}{runtime_text}

Source Code:
{request.original_source}
"""
        # First attempt
        response = self.llm.chat(SYSTEM_PROMPT, user_prompt, self.tracker)

        if response.error:
            return RepairResult(
                file_path=request.file_path,
                repaired_source=request.original_source,
                explanation=f"LLM error: {response.error}",
                compiles=False,
                validation_error=response.error,
            )

        clean_code = self._strip_fences(response.content)

        # Compile validation
        is_valid, syntax_error = self._validate_compile(clean_code, request.file_path)

        if is_valid:
            return RepairResult(
                file_path=request.file_path,
                repaired_source=clean_code,
                explanation=f"Repaired {len(request.current_findings)} findings via {response.model}",
                compiles=True,
            )

        # Self-correction retry: feed the SyntaxError back to the LLM
        retry_prompt = (
            user_prompt
            + f"\n\n## Your previous response had a Python syntax error:\n"
            f"  {syntax_error}\n"
            "Fix this syntax error. Ensure every 'try' block has a matching "
            "'except' or 'finally'. Ensure all imports are present. "
            "Return the COMPLETE corrected file."
        )

        response = self.llm.chat(SYSTEM_PROMPT, retry_prompt, self.tracker)

        if response.error:
            return RepairResult(
                file_path=request.file_path,
                repaired_source=request.original_source,
                explanation=f"LLM retry error: {response.error}",
                compiles=False,
                validation_error=response.error,
            )

        clean_code = self._strip_fences(response.content)
        is_valid, syntax_error = self._validate_compile(clean_code, request.file_path)

        if is_valid:
            return RepairResult(
                file_path=request.file_path,
                repaired_source=clean_code,
                explanation=f"Repaired {len(request.current_findings)} findings via {response.model} (after retry)",
                compiles=True,
            )

        # Both attempts failed: return original code unchanged
        return RepairResult(
            file_path=request.file_path,
            repaired_source=request.original_source,
            explanation=f"LLM returned invalid Python after retry: {syntax_error}",
            compiles=False,
            validation_error=str(syntax_error),
        )

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Strip markdown code fences from LLM output."""
        text = text.strip()
        if BT in text:
            pattern = rf"{BT}(?:python)?\s*(.*?)\s*{BT}"
            blocks = re.findall(pattern, text, re.DOTALL)
            if blocks:
                text = "\n".join(blocks)
            else:
                lines = text.splitlines()
                text = "\n".join(line for line in lines if not line.strip().startswith(BT))
        return text.strip()

    @staticmethod
    def _validate_compile(code: str, filename: str) -> tuple[bool, str | None]:
        """Check if code compiles. Returns (is_valid, error_message)."""
        try:
            compile(code, filename, "exec")
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}: {e.msg}"