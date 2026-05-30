"""Optional SonarQube static analyzer.

SonarQube is organised around an ISO/IEC 25010-style quality model
(reliability, security, maintainability ratings), which makes it a natural
higher-fidelity source for the iso25010_base profile. This analyzer is
*optional*: it runs only when SONARQUBE_URL and SONARQUBE_TOKEN are set,
and otherwise no-ops so the pipeline keeps working offline on Radon/Bandit
(the complement-with-fallback decision).

Deployment: targets a self-hosted SonarQube Server (``docker run -d -p
9000:9000 sonarqube``) plus the ``sonar-scanner`` CLI. Pointing
SONARQUBE_URL at https://sonarcloud.io and setting SONARQUBE_ORGANIZATION
switches to SonarCloud with no code change.

Flow when configured:
  1. Materialise the code unit into a throwaway project directory with a
     sonar-project.properties pointing at the server.
  2. Run sonar-scanner, which uploads analysis to the server.
  3. Poll the Web API: GET /api/issues/search for findings, and
     GET /api/measures/component for the ratings, which are attached to
     the RawToolResult.stdout as a JSON blob the evaluators read.

Because the sandbox has no SonarQube server, the network/scan path is
guarded and unit-tested via the normalizer and the no-op behaviour; the
live path is exercised when a server is configured.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import uuid
from pathlib import Path

from qallm.analysis.analysis_model import RawToolResult
from qallm.analysis.base_analyzer import StaticCodeAnalyzer
from qallm.analysis.normalization.base_normalizer import ToolNormalizer
from qallm.analysis.normalization.sonarqube_normalizer import SonarQubeNormalizer
from qallm.common.model import CodeUnit
from qallm.config import settings

logger = logging.getLogger(__name__)

# Measure keys requested from the Web API. These are the ISO/IEC
# 25010-aligned ratings SonarQube computes (1.0=A .. 5.0=E) plus the raw
# issue counts behind them.
_MEASURE_KEYS = [
    "reliability_rating",
    "security_rating",
    "sqale_rating",  # maintainability rating
    "bugs",
    "vulnerabilities",
    "code_smells",
    "coverage",
    "ncloc",
]


class SonarQubeAnalyzer(StaticCodeAnalyzer):
    """Static analysis via a SonarQube server (optional).

    When unconfigured, ``analyze`` returns a result with exit code 0 and an
    empty issue payload, so it contributes no findings and the manager's
    normalization yields nothing. ``is_configured`` lets the manager decide
    whether to include it at all.
    """

    def __init__(self) -> None:
        super().__init__()
        self.name = "sonarqube"
        self.normalizer = SonarQubeNormalizer()

    def tool_name(self) -> str:
        return self.name

    def get_normalizer(self) -> ToolNormalizer:
        return self.normalizer

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.SONARQUBE_URL and settings.SONARQUBE_TOKEN)

    def analyze(self, unit: CodeUnit) -> RawToolResult:
        if not self.is_configured():
            # Not configured: contribute nothing, let Radon/Bandit stand.
            return RawToolResult(
                tool=self.name,
                exit_code=0,
                stdout=json.dumps({"issues": [], "measures": {},
                                   "skipped": "SonarQube not configured"}),
                stderr="",
            )

        project_key = f"qallm_{uuid.uuid4().hex[:12]}"
        try:
            issues, measures = self._scan(unit, project_key)
            payload = {"issues": issues, "measures": measures}
            return RawToolResult(
                tool=self.name,
                exit_code=0,
                stdout=json.dumps(payload),
                stderr="",
                artifact=str(unit.original_path.absolute())
                if unit.original_path else "cell.py",
            )
        except Exception as exc:  # noqa: BLE001 - never break the pipeline
            logger.warning("SonarQube analysis failed (%s); falling back.", exc)
            return RawToolResult(
                tool=self.name, exit_code=1,
                stdout=json.dumps({"issues": [], "measures": {}}),
                stderr=str(exc),
            )

    # ─── live scan path (exercised when a server is configured) ─────
    def _scan(self, unit: CodeUnit, project_key: str) -> tuple[list, dict]:
        """Run the scanner and fetch issues + measures. Network-dependent."""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            filename = unit.original_path.name if unit.original_path else "cell.py"
            (workspace / filename).write_text(unit.source_code, encoding="utf-8")
            self._write_scanner_props(workspace, project_key)
            self._run_scanner(workspace)
            issues = self._fetch_issues(project_key)
            measures = self._fetch_measures(project_key)
            return issues, measures

    def _write_scanner_props(self, workspace: Path, project_key: str) -> None:
        lines = [
            f"sonar.projectKey={project_key}",
            f"sonar.host.url={settings.SONARQUBE_URL}",
            f"sonar.token={settings.SONARQUBE_TOKEN}",
            "sonar.sources=.",
            "sonar.python.version=3",
        ]
        if settings.SONARQUBE_ORGANIZATION:
            lines.append(f"sonar.organization={settings.SONARQUBE_ORGANIZATION}")
        (workspace / "sonar-project.properties").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def _run_scanner(self, workspace: Path) -> None:
        subprocess.run(
            [settings.SONARQUBE_SCANNER],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=settings.SONARQUBE_TIMEOUT_SECONDS,
            check=False,
        )

    def _api_get(self, path: str, params: dict) -> dict:
        # Imported lazily so requests is only needed when SonarQube is used.
        import requests

        resp = requests.get(
            f"{settings.SONARQUBE_URL.rstrip('/')}{path}",
            params=params,
            auth=(settings.SONARQUBE_TOKEN, ""),
            timeout=settings.SONARQUBE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()

    def _fetch_issues(self, project_key: str) -> list:
        data = self._api_get("/api/issues/search",
                             {"componentKeys": project_key, "ps": 500})
        return data.get("issues", [])

    def _fetch_measures(self, project_key: str) -> dict:
        data = self._api_get("/api/measures/component", {
            "component": project_key,
            "metricKeys": ",".join(_MEASURE_KEYS),
        })
        measures = {}
        for m in data.get("component", {}).get("measures", []):
            measures[m.get("metric")] = m.get("value")
        return measures
