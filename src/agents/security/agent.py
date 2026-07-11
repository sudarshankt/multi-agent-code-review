"""SecurityAgent: RAG-augmented LLM security analysis."""

from __future__ import annotations

from typing import Any

from src.agents.base import BaseAnalysisAgent
from src.agents.parsing import findings_from_llm
from src.agents.security.retriever import SecurityRetriever
from src.core.constants import AGENT_SECURITY
from src.models.finding import Category, Finding
from src.prompts.loader import render
from src.services.llm_service import LLMService, get_llm_service


class SecurityAgent(BaseAnalysisAgent):
    name = AGENT_SECURITY

    def __init__(
        self,
        llm: LLMService | None = None,
        retriever: SecurityRetriever | None = None,
    ) -> None:
        self.llm = llm or get_llm_service()
        self.retriever = retriever or SecurityRetriever()

    async def _static_triage(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        keywords = ["import os", "subprocess", "eval", "exec", "requests", "open(", "pickle"]
        if any(keyword in code for keyword in keywords):
            return [{"type": "keyword", "keyword": "suspicious-pattern"}]
        return []

    async def analyze(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[Finding]:
        rag_context = self.retriever.retrieve(code)
        diff = (context or {}).get("diffs", {}).get(file_path, "")
        prompt = render(
            "security.j2",
            file_path=file_path,
            code=code,
            rag_context=rag_context,
            diff=diff,
        )
        payload = await self.llm.complete_json(prompt)
        findings = findings_from_llm(payload, Category.SECURITY, file_path)
        for finding in findings:
            finding.agent_name = self.name
        return findings
