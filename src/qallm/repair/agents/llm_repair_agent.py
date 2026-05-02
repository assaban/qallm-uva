import re
from qallm.llm.base import LLMModel
from qallm.repair.repair_model import RepairResult, RepairRequest
from qallm.repair.repair_orchestration import RepairAgent

# Using character codes for backticks to prevent breaking the display formatting
BT = chr(96) * 3

SYSTEM_PROMPT = """
You are a senior Python security and quality engineer.
Fix the code to address ALL the provided static analysis findings with minimal changes.

Rules:
1. Preserve external behavior unless a finding requires changing it for safety.
2. Do not introduce new dependencies unless explicitly allowed.
3. Prefer safe standard-library alternatives (e.g. ast.literal_eval over eval, 
   subprocess with list args over shell=True).
4. Remove hardcoded secrets and replace with os.environ reads (never print secrets).
5. If a finding is a false positive or cannot be fixed safely, keep the 
   original code unchanged and add a # noqa comment on the relevant line.
6. Keep changes small and localized, fix only the reported issues.
7. Return the COMPLETE corrected file. No explanations, no markdown fences, 
   no partial snippets. Return the full file from first line to last line.
"""


class LLMRepairAgent(RepairAgent):
    """
    Concrete implementation of RepairAgent using an LLM.
    Handles code extraction and token tracking for cost analysis.
    """

    def __init__(self, llm: LLMModel):
        self.llm = llm

    def repair(self, request: RepairRequest) -> RepairResult:
        """
        Invokes the LLM to repair a file based on a bundle of findings.
        """
        # Construct the context of issues for the LLM
        findings_text = "\n".join([
            f"- {f.rule_id} (line {f.line}): {f.message}"
            for f in request.current_findings
        ])

        user_prompt = f"""
File: {request.file_path}
Findings:
{findings_text}

Source Code:
{request.original_source}
"""
        # Execute chat completion using the provided token tracker for cost analysis
        response = self.llm.chat(SYSTEM_PROMPT, user_prompt, self.llm.token_tracker())

        # 1. Capture content
        clean_code = response.content

        # 2. Logic Continuity: Strip markdown fences if the LLM ignored the rules
        if BT in clean_code:
            # We use the BT variable to avoid literal triple backticks in this regex string
            pattern = rf"{BT}(?:python)?\s*(.*?)\s*{BT}"
            blocks = re.findall(pattern, clean_code, re.DOTALL)
            if blocks:
                # If there are multiple blocks, we join them (the agent expects one full file)
                clean_code = "\n".join(blocks)
            else:
                # Fallback: manually strip lines that start with backticks if fences are malformed
                lines = clean_code.splitlines()
                cleaned_lines = [l for l in lines if not l.strip().startswith(BT)]
                clean_code = "\n".join(cleaned_lines)

        # 3. RepairResult Alignment: Return a clean object for the RepairManager
        return RepairResult(
            file_path=request.file_path,
            repaired_source=clean_code.strip(),
            explanation="Automated LLM Repair based on static analysis findings.",
            compiles=False  # This field is updated later by the RepairManager via ast.parse
        )