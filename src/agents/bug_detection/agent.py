"""BugDetectionAgent: AST analyzers (Python) + LLM."""

from __future__ import annotations

from typing import Any

from src.agents.base import BaseAnalysisAgent
from src.agents.bug_detection.analyzers import run_all
from src.agents.parsing import findings_from_llm
from src.core.constants import AGENT_BUG, PYTHON_EXTENSIONS
from src.core.logging import get_logger
from src.models.finding import Category, Finding
from src.prompts.loader import render
from src.services.llm_service import LLMService, get_llm_service

logger = get_logger(__name__)


class BugDetectionAgent(BaseAnalysisAgent):
    name = AGENT_BUG

    def __init__(self, llm: LLMService | None = None) -> None:
        self.llm = llm or get_llm_service()

    async def _static_triage(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        suspicious_tokens = ["raise ", "except", "try:", "return", "assert", "open(", "with "]
        if any(token in code for token in suspicious_tokens):
            return [{"type": "syntax-signal", "token": "control-flow"}]
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
            "bug_detection.j2",
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
        llm_findings = findings_from_llm(payload, Category.BUG, file_path)
        logger.info(
            "llm_prompt_preview",
            llm_findings=llm_findings,
            ast_findings=static_findings
        )
        return static_findings + llm_findings
