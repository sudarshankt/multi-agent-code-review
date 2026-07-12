"""Integration test for SecurityAgent with Graph-Based Context Stitching."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.security.agent import SecurityAgent


class TestSecurityAgentStitching:
    """Validates that the SecurityAgent correctly traces, extracts, and stitches code from imports."""

    @pytest.mark.asyncio
    async def test_security_agent_stitches_local_dependency_context(self) -> None:
        """The agent should locate imported helper functions and inject their code into the final LLM prompt."""
        # 1. Setup Mock LLM that captures the compiled prompt
        mock_llm = AsyncMock()
        mock_llm.complete_json.return_value = []  # Return zero findings for this test boundary

        # 2. Setup Mock RAG retriever
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = "- CWE-89 SQL Injection: use parameterized queries."

        # 3. Instantiate the agent with mocked IO boundaries
        agent = SecurityAgent(llm=mock_llm, retriever=mock_retriever)

        # 4. Define a mock multi-file repository structure
        # routes.py is under review, utils/security.py is unmodified but imported.
        files_dict = {
            "app/routes.py": (
                "from utils.security import sanitize_input\n"
                "def handle_request(user_input):\n"
                "    clean = sanitize_input(user_input)\n"
                "    db.execute(f'SELECT * FROM users WHERE name = {clean}')"
            ),
            "utils/security.py": (
                "def sanitize_input(val):\n"
                "    # Only strips whitespace - does NOT prevent SQL Injection!\n"
                "    return val.strip()\n"
            ),
        }

        # 5. Build the LangGraph State Context
        context = {
            "triage_enabled": False,  # Bypasses local Bandit checks for this specific test
            "files": files_dict,
            "diffs": {
                "app/routes.py": "+    clean = sanitize_input(user_input)\n"
            },
            "dependency_cache": {},   # Shared transient cache
        }

        # 6. Execute the agent run on the modified files list
        # We only pass routes.py as the file "under review" in the diff
        under_review_files = {"app/routes.py": files_dict["app/routes.py"]}
        findings = await agent.run(under_review_files, context)

        # --- VERIFICATIONS ---

        # Verify findings list returned safely
        assert isinstance(findings, list)

        # Capture the raw prompt that was rendered and sent to the LLM
        mock_llm.complete_json.assert_called_once()
        rendered_prompt = mock_llm.complete_json.call_args[0][0]

        # Check 1: RAG Context was injected
        assert "CWE-89 SQL Injection: use parameterized queries." in rendered_prompt

        # Check 2: The Diff was injected
        assert "+    clean = sanitize_input(user_input)" in rendered_prompt

        # Check 3: The Untrusted Input Notice is intact
        assert "UNTRUSTED INPUT NOTICE" in rendered_prompt

        # Check 4: GRAPH-BASED CONTEXT STITCHING PROOF
        # The AST resolver must have successfully parsed routes.py, tracked the utils.security import,
        # opened utils/security.py, extracted the function, and stitched it into the prompt.
        assert "IMPORTED DEPENDENCY DEFINITIONS" in rendered_prompt
        assert "File: `utils/security.py`" in rendered_prompt
        assert "Symbol: `sanitize_input`" in rendered_prompt
        assert "def sanitize_input(val):" in rendered_prompt
        assert "# Only strips whitespace - does NOT prevent SQL Injection!" in rendered_prompt