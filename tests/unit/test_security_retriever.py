"""Unit tests for SecurityRetriever — RAG query, fallback, and formatting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.agents.security.retriever import SecurityRetriever


class TestSecurityRetriever:
    """Tests for the SecurityRetriever covering ChromaDB and fallback paths."""

    def test_retrieve_falls_back_when_chromadb_unavailable(self) -> None:
        """When ChromaDB is unavailable, the retriever returns hardcoded OWASP knowledge."""
        retriever = SecurityRetriever(top_k=3)

        with patch.object(retriever, "_query_chromadb", return_value=[]):
            result = retriever.retrieve("some code with sql injection")

        # Should contain fallback knowledge formatted with bullet points
        assert result.startswith("- CWE-")
        # top_k=3 => exactly 3 entries
        assert len(result.split("\n")) == 3
        # Verify content comes from fallback
        assert "SQL Injection" in result

    def test_retrieve_falls_back_when_chromadb_raises(self) -> None:
        """When ChromaDB raises an exception, fallback knowledge is returned."""
        retriever = SecurityRetriever(top_k=5)

        with patch.object(
            retriever, "_query_chromadb", side_effect=RuntimeError("chromadb crash")
        ):
            result = retriever.retrieve("some code")

        # Should still return valid fallback content
        assert result.startswith("- CWE-")
        assert len(result.split("\n")) == 5
        bullet_count = result.count("\n- CWE-")
        assert bullet_count == 4  # first entry starts after \n, then 4 more \n-

    def test_retrieve_uses_chromadb_when_available(self) -> None:
        """When ChromaDB returns documents, they are used instead of fallback."""
        chroma_docs = [
            "CWE-89 SQL Injection: use parameterized queries.",
            "CWE-79 XSS: escape output.",
            "CWE-798 Hardcoded Credentials: use env vars.",
        ]
        retriever = SecurityRetriever(top_k=3)

        with patch.object(retriever, "_query_chromadb", return_value=chroma_docs):
            result = retriever.retrieve("some code")

        # Should use ChromaDB docs, not fallback
        assert "parameterized queries" in result
        assert "escape output" in result
        assert len(result.split("\n")) == 3

    def test_default_top_k_is_five(self) -> None:
        """Default top_k should be 5, matching the design spec."""
        retriever = SecurityRetriever()
        assert retriever.top_k == 5

    def test_top_k_bounds_fallback_results(self) -> None:
        """top_k properly limits the number of fallback entries returned."""
        retriever = SecurityRetriever(top_k=1)

        with patch.object(retriever, "_query_chromadb", return_value=[]):
            result = retriever.retrieve("code")

        assert len(result.split("\n")) == 1

    def test_bullet_formatting(self) -> None:
        """Retrieved documents are formatted as markdown bullet points."""
        retriever = SecurityRetriever(top_k=3)
        docs = ["Doc A", "Doc B", "Doc C"]

        with patch.object(retriever, "_query_chromadb", return_value=docs):
            result = retriever.retrieve("code")

        expected = "- Doc A\n- Doc B\n- Doc C"
        assert result == expected

    def test_code_truncation_for_rag_query(self) -> None:
        """Code longer than MAX_CODE_CHARS_FOR_RAG is truncated before querying."""
        retriever = SecurityRetriever(top_k=3)
        # Create code longer than the 2000-char limit
        long_code = "x" * 5000

        captured_query: str | None = None

        def _capture_query(query: str) -> list[str]:
            nonlocal captured_query
            captured_query = query
            return []

        with patch.object(retriever, "_query_chromadb", side_effect=_capture_query):
            retriever.retrieve(long_code)

        assert captured_query is not None
        assert len(captured_query) == 2000
        assert captured_query == "x" * 2000

    def test_empty_code_handled(self) -> None:
        """Empty code string is handled gracefully."""
        retriever = SecurityRetriever(top_k=3)

        with patch.object(retriever, "_query_chromadb", return_value=[]):
            result = retriever.retrieve("")

        # Should still return fallback knowledge
        assert len(result) > 0
        assert result.startswith("- CWE-")
