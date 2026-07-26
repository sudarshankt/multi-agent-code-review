"""Base class for analysis agents."""

from __future__ import annotations

import asyncio
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

    async def _static_triage(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]] | None:
        """
        Return lightweight local signals that suggest deeper review is warranted.
        
        Architectural Contract:
        - Return `[...]` (list of alerts): Proceed to LLM and pass these alerts as hints.
        - Return `[]` (empty list): Static checks passed completely. Safe to SKIP the LLM.
        - Return `None` (default): Triage is unsupported/skipped for this agent. ALWAYS run LLM.
        """
        return None

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
        base_context = dict(context or {})
        caller_context = context or {}
        findings: list[Finding] = []
        started = time.monotonic()
        semaphore = asyncio.Semaphore(5)
        triage_enabled = bool(base_context.get("triage_enabled"))

        async def process_file(file_path: str, code: str) -> list[Finding]:
            file_started = time.monotonic()
            if not self._supported(file_path):
                return []

            sem_wait_started = time.monotonic()
            async with semaphore:
                sem_wait = time.monotonic() - sem_wait_started
                try:
                    file_context = dict(base_context)

                    if triage_enabled:
                        triage_started = time.monotonic()
                        triage_alerts = await self._static_triage(code, file_path, file_context)
                        triage_duration = time.monotonic() - triage_started

                        if triage_alerts is not None and len(triage_alerts) == 0:
                            files_bypassed = int(base_context.get("files_bypassed", 0)) + 1
                            base_context["files_bypassed"] = files_bypassed
                            caller_context["files_bypassed"] = files_bypassed
                            file_context["files_bypassed"] = files_bypassed
                            logger.info(
                                "agent_triage_skipped",
                                agent_name=self.name,
                                file=file_path,
                                alerts=0,
                                files_bypassed=files_bypassed,
                                triage_duration_seconds=round(triage_duration, 3),
                            )
                            return []

                        file_context["triage_alerts"] = triage_alerts or []
                    else:
                        triage_duration = 0.0
                        file_context["triage_alerts"] = []

                    analyze_started = time.monotonic()
                    file_findings = await self.analyze(code, file_path, file_context)
                    analyze_duration = time.monotonic() - analyze_started

                except Exception as exc:  # noqa: BLE001 - one bad file must not halt the agent
                    logger.warning(
                        "agent_file_failed",
                        agent_name=self.name,
                        file=file_path,
                        error=str(exc),
                        duration_seconds=round(time.monotonic() - file_started, 3),
                    )
                    return []

            total_file_duration = time.monotonic() - file_started
            logger.info(
                "agent_file_processed",
                agent_name=self.name,
                file=file_path,
                findings=len(file_findings),
                sem_wait_seconds=round(sem_wait, 3),
                triage_seconds=round(triage_duration, 3),
                analyze_seconds=round(analyze_duration, 3),
                total_seconds=round(total_file_duration, 3),
            )

            for finding in file_findings:
                finding.agent_name = self.name
            return file_findings

        tasks = [process_file(file_path, code) for file_path, code in files.items()]
        results = await asyncio.gather(*tasks)

        for file_findings in results:
            findings.extend(file_findings)

        logger.info(
            "agent_run_complete",
            agent_name=self.name,
            files=len(files),
            findings=len(findings),
            files_bypassed=base_context.get("files_bypassed", 0),
            duration_seconds=round(time.monotonic() - started, 3),
        )
        return findings