"""PerformanceAgent: AST complexity/memory/hotspot analyzers + LLM."""

from __future__ import annotations

from typing import Any

from src.agents.base import BaseAnalysisAgent
from src.agents.parsing import findings_from_llm
from src.agents.performance.analyzers import run_all
from src.core.constants import AGENT_PERFORMANCE, PYTHON_EXTENSIONS
from src.models.finding import Category, Finding
from src.prompts.loader import render
from src.services.llm_service import LLMService, get_llm_service


class PerformanceAgent(BaseAnalysisAgent):
    name = AGENT_PERFORMANCE

    def __init__(self, llm: LLMService | None = None) -> None:
        self.llm = llm or get_llm_service()

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
        prompt = render(
            "performance.j2", file_path=file_path, code=code, static_findings=hints
        )
        payload = await self.llm.complete_json(prompt)
        llm_findings = findings_from_llm(payload, Category.PERFORMANCE, file_path)
        return static_findings + llm_findings
