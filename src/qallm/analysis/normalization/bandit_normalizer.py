import json
from qallm.analysis.models import Finding
from .base import NormalizationContext, ToolNormalizer
# from .util import get_rel_path, get_snippet

class BanditNormalizer(ToolNormalizer):
    tool_name = "bandit"

    def normalize(self, raw: dict, ctx: NormalizationContext) -> list[Finding]:
        artifact = raw.get("artifact") or "bandit.json"
        p = ctx.reports_dir / artifact
        if not p.exists(): return []

        try:
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
        except: return []

        findings = []
        for issue in data.get("results", []):
            file_path = issue.get("filename")
            # Handle cases where Bandit reports <stdin>
            if file_path == "<stdin>":
                # Fallback to a known file in workspace if only one exists
                files = list(ctx.workspace_dir.glob("*.py"))
                file_rel = files[0].name if files else "source.py"
            else:
                file_rel = get_rel_path(ctx.workspace_dir, file_path)

            line = issue.get("line_number", 1)
            findings.append(Finding(
                tool="bandit",
                type="SECURITY",
                severity=issue.get("issue_severity", "LOW"),
                file=file_rel,
                line=line,
                message=issue.get("issue_text", ""),
                rule_id=issue.get("test_id", ""),
                code_snippet=get_snippet(ctx.workspace_dir, file_rel, line),
                extra={
                    "confidence": issue.get("issue_confidence"),
                    "cwe": issue.get("issue_cwe")
                }
            ))
        return findings