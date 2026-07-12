"""StyleAgent: Ruff linter (if available) + LLM style/readability analysis."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from src.agents.base import BaseAnalysisAgent
from src.agents.parsing import findings_from_llm
from src.core.constants import AGENT_STYLE, PYTHON_EXTENSIONS
from src.core.logging import get_logger
from src.models.finding import Category, Finding, Location, Severity
from src.prompts.loader import render
from src.services.llm_service import LLMService, get_llm_service

logger = get_logger(__name__)


class StyleAgent(BaseAnalysisAgent):
    name = AGENT_STYLE

    def __init__(self, llm: LLMService | None = None) -> None:
        self.llm = llm or get_llm_service()

    async def _static_triage(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if any(token in code for token in ["import ", "def ", "class ", "return"]):
            return [{"type": "structure", "token": "python-structure"}]
        return []

    async def analyze(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[Finding]:
        ruff_findings = self._run_ruff(code, file_path) if file_path.endswith(
            PYTHON_EXTENSIONS
        ) else []
        ruff_hints = [
            {"start_line": f.location.start_line, "code": getattr(f, "code", "?"), "title": f.title}
            for f in ruff_findings
        ]

        diff = (context or {}).get("diffs", {}).get(file_path, "")
        prompt = render(
            "style.j2",
            file_path=file_path,
            code=code,
            ruff_issues=ruff_hints,
            diff=diff,
        )
        logger.info(
            "llm_prompt_preview",
            agent_name=self.name,
            file=file_path,
            code_chars=len(code),
            diff_chars=len(diff),
            ruff_hints_count=len(ruff_hints),
            prompt_total_chars=len(prompt),
        )
        payload = await self.llm.complete_json(prompt)
        llm_findings = findings_from_llm(payload, Category.STYLE, file_path)

        # Do not duplicate Ruff findings in the LLM response.
        ruff_titles = {f.title.lower() for f in ruff_findings}
        deduped_llm = [
            f for f in llm_findings if f.title.lower() not in ruff_titles
        ]
        return ruff_findings + deduped_llm

    def _run_ruff(self, code: str, file_path: str) -> list[Finding]:
        try:
            result = subprocess.run(
                ["ruff", "check", "--output-format", "json", "--select", "E,W,F"],
                input=code.encode(),
                capture_output=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("ruff_unavailable", file=file_path)
            return []

        try:
            data = json.loads(result.stdout.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []

        findings: list[Finding] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            code_val = item.get("code", "?")
            msg = item.get("message", "")
            line = item.get("location", {}).get("row")
            if not line:
                continue
            findings.append(
                Finding(
                    category=Category.STYLE,
                    severity=Severity.LOW,
                    title=f"{code_val}: {msg[:50]}",
                    description=msg,
                    location=Location(file_path=file_path, start_line=line, end_line=line),
                    code=code_val,
                )
            )
        return findings
