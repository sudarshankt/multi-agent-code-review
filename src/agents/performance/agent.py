"""PerformanceAgent: AST complexity/memory/hotspot analyzers + LLM."""

from __future__ import annotations

from typing import Any

from src.agents.base import BaseAnalysisAgent
from src.agents.parsing import findings_from_llm
from src.agents.performance.analyzers import run_all
from src.core.constants import AGENT_PERFORMANCE, PYTHON_EXTENSIONS
from src.core.logging import get_logger
from src.models.finding import Category, Finding
from src.prompts.loader import render
from src.services.llm_service import LLMService, get_llm_service

logger = get_logger(__name__)


class PerformanceAgent(BaseAnalysisAgent):
    name = AGENT_PERFORMANCE

    def __init__(self, llm: LLMService | None = None) -> None:
        self.llm = llm or get_llm_service()

    async def _static_triage(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if any(token in code for token in ["for ", "while ", "sum(", "list(", "dict("]):
            return [{"type": "loop-pattern", "token": "iteration"}]
        return []

    async def analyze(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[Finding]:
        static_findings: list[Finding] = []
        if file_path.endswith(PYTHON_EXTENSIONS):
            static_findings = run_all(code, file_path)

        hints = [
            {"start_line": f.location.start_line, "title": f.title}
            for f in static_findings
        ]
        diff = (context or {}).get("diffs", {}).get(file_path, "")
        prompt = render(
            "performance.j2",
            file_path=file_path,
            code=code,
            static_findings=hints,
            diff=diff,
        )
        logger.info(
            "llm_prompt_preview",
            agent_name=self.name,
            file=file_path,
            code_chars=len(code),
            diff_chars=len(diff),
            hints_count=len(hints),
            prompt_total_chars=len(prompt),
        )
        payload = await self.llm.complete_json(prompt)
        llm_findings = findings_from_llm(payload, Category.PERFORMANCE, file_path)
        return static_findings + llm_findings
