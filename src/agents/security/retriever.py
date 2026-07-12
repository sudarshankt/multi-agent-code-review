"""Security knowledge retriever.

Queries ChromaDB for the most relevant OWASP/CWE entries (top-5). If ChromaDB or
its embedding stack is unavailable, falls back to a small hardcoded knowledge set
so the SecurityAgent always has context (graceful degradation, spec decision #4).
"""

from __future__ import annotations

from src.core.constants import MAX_CODE_CHARS_FOR_RAG
from src.core.logging import get_logger

logger = get_logger(__name__)

# Minimal hardcoded fallback knowledge.
_FALLBACK_KNOWLEDGE = [
    "CWE-89 SQL Injection: never build SQL with string concatenation/format; use "
    "parameterized queries or an ORM.",
    "CWE-78 OS Command Injection: avoid passing untrusted input to shell; use "
    "subprocess with a list of args and shell=False.",
    "CWE-79 Cross-site Scripting: escape/encode untrusted data before rendering in HTML.",
    "CWE-22 Path Traversal: validate and normalize file paths; reject '..' segments.",
    "CWE-798 Hardcoded Credentials: never commit secrets; load from env/secret manager.",
    "CWE-327 Weak Crypto: avoid MD5/SHA1 for security; use strong, salted hashing.",
    "CWE-502 Insecure Deserialization: do not unpickle/yaml.load untrusted data.",
    "CWE-918 SSRF: validate outbound URLs; block internal address ranges.",
]


class SecurityRetriever:
    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def retrieve(self, code: str) -> str:
        query = code[:MAX_CODE_CHARS_FOR_RAG]
        
        # Defensive programming block:
        # Wrap the call to _query_chromadb to catch mock exceptions or unexpected errors.
        try:
            docs = self._query_chromadb(query)
        except Exception as exc:
            logger.warning("security_rag_query_failed", error=str(exc))
            docs = []

        if not docs:
            docs = _FALLBACK_KNOWLEDGE[: self.top_k]
            logger.info("security_rag_fallback", source="hardcoded_owasp", count=len(docs))
        else:
            logger.info("security_rag_retrieved", source="chromadb", count=len(docs))
            
        return "\n".join(f"- {d}" for d in docs)

    def _query_chromadb(self, query: str) -> list[str]:
        try:
            from src.infrastructure.chromadb.client import query_knowledge

            return query_knowledge(query, top_k=self.top_k)
        except Exception:
            return []