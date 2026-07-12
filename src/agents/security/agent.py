"""SecurityAgent: RAG-augmented LLM security analysis."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Any

from src.agents.base import BaseAnalysisAgent
from src.agents.parsing import findings_from_llm
from src.agents.security.retriever import SecurityRetriever
from src.core.constants import AGENT_SECURITY
from src.models.finding import Category, Finding
from src.prompts.loader import render
from src.services.llm_service import LLMService, get_llm_service
from src.agents.dependency_resolver import stitch_context  # IMPORT STITCHER

logger = logging.getLogger(__name__)

class SecurityAgent(BaseAnalysisAgent):
    name = AGENT_SECURITY
    _SECRET_PATTERNS = (
        re.compile(r"sk_live_[A-Za-z0-9_\-]{10,}"),
        re.compile(r"ghp_[A-Za-z0-9]{20,}"),
        re.compile(r"github_pat_[A-Za-z0-9_\-]{20,}"),
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----"),
    )

    def __init__(
        self,
        llm: LLMService | None = None,
        retriever: SecurityRetriever | None = None,
    ) -> None:
        self.llm = llm or get_llm_service()
        self.retriever = retriever or SecurityRetriever()

    def _sanitize_content(self, content: str, *, max_chars: int = 8000) -> str:
        """Redact likely secrets and trim large content before sending to the LLM."""
        if not content:
            return ""

        sanitized = content
        for pattern in self._SECRET_PATTERNS:
            sanitized = pattern.sub("<redacted>", sanitized)

        sanitized = sanitized.replace("\r\n", "\n")
        if len(sanitized) > max_chars:
            sanitized = sanitized[:max_chars] + "\n... [truncated]"
        return sanitized

    async def _static_triage(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Run Bandit for Python files, fallback to keyword matching."""
        alerts = []
        
        # 1. Check if file is empty (only safe time to skip Security LLM)
        if not code.strip():
            return [] # Returning empty list safely skips the LLM in BaseAnalysisAgent
            
        # 2. Try running Bandit (Industry Standard Python SAST)
        if file_path.endswith(".py"):
            try:
                # Note: We pass code via stdin or temporary file, but for simplicity 
                # here we assume file_path exists on disk or we fallback to keywords.
                result = subprocess.run(
                    ["bandit", "-f", "json", "-q", file_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.stdout:
                    bandit_data = json.loads(result.stdout)
                    for issue in bandit_data.get("results", []):
                        alerts.append({
                            "source": "bandit",
                            "issue": issue.get("issue_text"),
                            "severity": issue.get("issue_severity"),
                            "line": issue.get("line_number")
                        })
            except Exception as e:
                logger.debug(f"Bandit triage failed on {file_path}, falling back to keywords: {e}")

        # 3. Fallback / Augment with Keyword Matching
        keywords = ["import os", "subprocess", "eval", "exec", "requests", "open(", "pickle", "SELECT", "<script>"]
        for keyword in keywords:
            if keyword in code:
                alerts.append({"source": "keyword_scanner", "keyword": keyword})
                
        # 4. ARCHITECTURAL SAFEGUARD:
        # If no alerts found, we STILL want the LLM to check for logic/context flaws (like IDOR).
        # We return a dummy "force_analysis" alert so BaseAnalysisAgent doesn't skip this file.
        if not alerts:
            alerts.append({"source": "system", "reason": "force_deep_security_scan"})
            
        return alerts

    async def analyze(
        self, code: str, file_path: str, context: dict[str, Any] | None = None
    ) -> list[Finding]:
        context = context or {}

        # 1. Gather Context & RAG
        rag_context = self.retriever.retrieve(code)
        diff = context.get("diffs", {}).get(file_path, "")

        # Extract the triage alerts we generated to pass them to the prompt.
        triage_alerts = context.get("triage_alerts", [])

        sanitized_code = self._sanitize_content(code)
        sanitized_diff = self._sanitize_content(diff)

        # 2. GRAPH-BASED CONTEXT STITCHING
        # Resolve GitHub client and repository info if available in context
        github_service = context.get("github_service")  # Passed from LangGraph orchestrator
        repo_info = context.get("repo_info")            # e.g., {"owner": "x", "repo": "y", "ref": "feat-branch"}
        files_dict = context.get("files", {})           # The in-memory dictionary of PR files
        transient_cache = context.get("dependency_cache", {}) # shared transient cache

        dependency_context = await stitch_context(
            code=code,
            file_path=file_path,
            files_dict=files_dict,
            github_service=github_service,
            repo_info=repo_info,
            transient_cache=transient_cache
        )

        # 2. Render Template
        prompt = render(
            "security.j2",
            file_path=file_path,
            code=sanitized_code,
            rag_context=rag_context,
            diff=sanitized_diff,
            triage_alerts=triage_alerts,
            dependency_context=dependency_context,
        )

        # 3. LLM Execution
        logger.info(
            "llm_prompt_preview",
            agent_name=self.name,
            file=file_path,
            code_chars=len(sanitized_code),
            diff_chars=len(sanitized_diff),
            rag_chars=len(rag_context or ""),
            dep_chars=len(dependency_context or ""),
            triage_count=len(triage_alerts),
            prompt_total_chars=len(prompt),
        )
        payload = await self.llm.complete_json(prompt)

        # 4. Parsing
        findings = findings_from_llm(payload, Category.SECURITY, file_path)
        for finding in findings:
            finding.agent_name = self.name

        return findings