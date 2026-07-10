"""Base class for analysis agents."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from src.core.constants import SOURCE_EXTENSIONS
from src.core.logging import get_logger
from src.models.finding import Finding

logger = get_logger(__name__)


class BaseAnalysisAgent(ABC):
    """Abstract analysis agent.

    Subclasses implement `analyze()` for a single file. The concrete `run()`
    iterates the candidate files, filters by SOURCE_EXTENSIONS, stamps the
    agent name onto findings, and isolates per-file failures.
    """

    #: stable identifier, e.g. "security"
    name: str = "base"

    @abstractmethod
    async def analyze(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[Finding]:
        """Return findings for a single file's content."""

    def _supported(self, file_path: str) -> bool:
        return file_path.endswith(SOURCE_EXTENSIONS)

    async def run(
        self, files: dict[str, str], context: dict[str, Any] | None = None
    ) -> list[Finding]:
        context = context or {}
        findings: list[Finding] = []
        started = time.monotonic()
        for file_path, code in files.items():
            if not self._supported(file_path):
                continue
            try:
                file_findings = await self.analyze(code, file_path, context)
            except Exception as exc:  # noqa: BLE001 - one bad file must not halt the agent
                logger.warning(
                    "agent_file_failed",
                    agent=self.name,
                    file=file_path,
                    error=str(exc),
                )
                continue
            for finding in file_findings:
                finding.agent_name = self.name
                findings.append(finding)
        logger.info(
            "agent_run_complete",
            agent=self.name,
            files=len(files),
            findings=len(findings),
            duration_seconds=round(time.monotonic() - started, 3),
        )
        return findings
