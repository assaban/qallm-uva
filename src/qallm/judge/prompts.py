"""Prompts for the ModelJudge.

Kept in a separate module so the wording can be reviewed independently
of the dispatch logic, and so it can be cited in the thesis methodology
chapter without pulling the implementation file.

Design notes
------------

The prompt asks for JSON. Asking for free text and trying to parse keywords
out of it produces unreliable verdicts. JSON gives us a machine-checkable
output and a structured place for the model to put its reasoning.

We do NOT include the source code of the parent or variant in the prompt.
v3 section 5.4: the judge reasons over evidence (the profile output and
raw verification numbers), not over the look of the code. This keeps the
judge from falling back to surface aesthetics.

The system prompt is short and frames the role. The user prompt carries
the data.
"""

from __future__ import annotations

import json
from typing import Any

from qallm.judge.models import VerdictComparison


SYSTEM_PROMPT = """\
You are a software quality judge for a research-software verification tool.
You will be shown a structured comparison of two variants of the same code
unit: a parent (the previous variant) and a candidate (the proposed new
variant). Each variant has been evaluated against a quality profile that
produces measured values for indicators across several quality dimensions.

Your job is to decide whether the candidate is an improvement, a regression,
or no meaningful change, given the evidence shown.

You must respond ONLY with a JSON object of this exact shape:

{
  "outcome": "improvement" | "regression" | "no_change",
  "explanation": "one paragraph, plain prose, no markdown",
  "confidence": <number between 0 and 1>
}

Rules:
- Base your verdict on the structured evidence shown. Do not assume facts
  that are not in the evidence.
- If indicator values improved in some dimensions but regressed in others,
  weigh them by importance. Security and Reliability regressions are more
  serious than Maintainability regressions.
- If the evidence is ambiguous, prefer "no_change" over inventing a verdict.
- If a dimension is SKIPPED on one or both sides, it does not contribute
  to your verdict.
"""


def build_user_prompt(
    comparison: VerdictComparison,
    raw_evidence: dict[str, Any] | None = None,
) -> str:
    """Build the user prompt for the model judge from a structured comparison.

    The prompt is one JSON-shaped object with two sections: ``comparison``
    (the structured diff) and ``raw_evidence`` (optional extras from
    verification: pass rates, bug counts, coverage numbers).
    """
    payload: dict[str, Any] = {
        "comparison": comparison.to_dict(),
    }
    if raw_evidence:
        payload["raw_evidence"] = raw_evidence

    body = json.dumps(payload, indent=2, default=str)
    return (
        "Below is the structured evidence comparing the parent variant to "
        "the candidate variant. Decide whether the candidate is an "
        "improvement, regression, or no_change, and respond with the JSON "
        "shape described in the system prompt.\n\n"
        f"```json\n{body}\n```"
    )
