"""Unit tests for the dependency resolver — import visiting, symbol extraction, and stitching."""

from __future__ import annotations

import ast
import textwrap
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.dependency_resolver import (
    ImportVisitor,
    SymbolExtractor,
    fetch_file_content,
    module_to_file_path,
    stitch_context,
)


class TestDependencyResolver:
    """Suite validating AST parsing, dependency extraction, and context stitching."""

    def test_module_to_file_path(self) -> None:
        """Verifies dot-notation modules correctly convert to file paths."""
        assert module_to_file_path("utils.security") == "utils/security.py"
        assert module_to_file_path("core.helpers.auth") == "core/helpers/auth.py"

    def test_import_visitor(self) -> None:
        """Visitor should identify local relative/absolute imports and skip external standard libraries."""
        code = textwrap.dedent("""
        import os
        from pydantic import BaseModel
        from utils.security import sanitize_input, hash_password
        from local_app.models import User
        """)
        tree = ast.parse(code)
        visitor = ImportVisitor(current_file="routes.py")
        visitor.visit(tree)

        # Should find exactly 3 symbols (2 from utils.security, 1 from local_app.models)
        # It ignores standard library 'os' and third-party 'pydantic'
        assert len(visitor.imports) == 3
        
        assert visitor.imports[0].module_path == "utils.security"
        assert visitor.imports[0].symbol_name == "sanitize_input"
        
        assert visitor.imports[1].module_path == "utils.security"
        assert visitor.imports[1].symbol_name == "hash_password"
        
        assert visitor.imports[2].module_path == "local_app.models"
        assert visitor.imports[2].symbol_name == "User"

    def test_symbol_extractor_function(self) -> None:
        """Extractor should locate and slice out only the target function definition from source code."""
        source = textwrap.dedent("""
        def irrelevant_func():
            return "skip me"

        def sanitize_input(val):
            # Target implementation
            return val.strip()

        class IrrelevantClass:
            pass
        """)
        tree = ast.parse(source)
        extractor = SymbolExtractor(target_symbol="sanitize_input", raw_source=source)
        extractor.visit(tree)

        assert extractor.extracted_source is not None
        assert "def sanitize_input(val):" in extractor.extracted_source
        assert "return val.strip()" in extractor.extracted_source
        assert "irrelevant_func" not in extractor.extracted_source

    def test_symbol_extractor_class(self) -> None:
        """Extractor should extract complete class definitions from source code."""
        source = textwrap.dedent("""
        class User:
            def __init__(self, name: str) -> None:
                self.name = name
        """)
        tree = ast.parse(source)
        extractor = SymbolExtractor(target_symbol="User", raw_source=source)
        extractor.visit(tree)

        assert extractor.extracted_source is not None
        assert "class User:" in extractor.extracted_source
        assert "self.name = name" in extractor.extracted_source

    @pytest.mark.asyncio
    async def test_fetch_file_content_from_pr(self) -> None:
        """Fetcher should immediately return file content if it belongs to the PR files dictionary."""
        files_dict = {"utils/security.py": "content_from_pr_diff"}
        cache: dict[str, str] = {}

        content = await fetch_file_content(
            file_path="utils/security.py",
            files_dict=files_dict,
            github_service=None,
            repo_info=None,
            cache=cache
        )

        assert content == "content_from_pr_diff"
        assert len(cache) == 0  # Cache remains clean because content was in PR files

    @pytest.mark.asyncio
    async def test_fetch_file_content_from_cache(self) -> None:
        """Fetcher should resolve dependencies from the transient memory cache if cached."""
        files_dict: dict[str, str] = {}
        cache = {"utils/security.py": "content_from_cache"}

        content = await fetch_file_content(
            file_path="utils/security.py",
            files_dict=files_dict,
            github_service=None,
            repo_info=None,
            cache=cache
        )

        assert content == "content_from_cache"

    @pytest.mark.asyncio
    async def test_fetch_file_content_from_github(self) -> None:
        """Fetcher falls back to querying the GitHub REST API and updates cache when successful."""
        files_dict: dict[str, str] = {}
        cache: dict[str, str] = {}
        
        mock_github = AsyncMock()
        mock_github.get_file_content.return_value = "content_from_github_api"
        repo_info = {"owner": "Team10", "repo": "capstone", "ref": "dev"}

        content = await fetch_file_content(
            file_path="utils/security.py",
            files_dict=files_dict,
            github_service=mock_github,
            repo_info=repo_info,
            cache=cache
        )

        assert content == "content_from_github_api"
        assert cache["utils/security.py"] == "content_from_github_api"
        mock_github.get_file_content.assert_called_once_with(
            "Team10", "capstone", "utils/security.py", "dev"
        )

    @pytest.mark.asyncio
    async def test_fetch_file_content_github_failure_returns_none(self) -> None:
        """Fetcher handles GitHub API failures gracefully, logging and returning None."""
        files_dict: dict[str, str] = {}
        cache: dict[str, str] = {}
        
        mock_github = AsyncMock()
        mock_github.get_file_content.side_effect = RuntimeError("API Limit reached")
        repo_info = {"owner": "Team10", "repo": "capstone"}

        content = await fetch_file_content(
            file_path="utils/security.py",
            files_dict=files_dict,
            github_service=mock_github,
            repo_info=repo_info,
            cache=cache
        )

        assert content is None
        assert len(cache) == 0

    @pytest.mark.asyncio
    async def test_stitch_context_integration_success(self) -> None:
        """Context stitching locates, parses, and formats the targeted helper module's AST."""
        code_under_review = "from utils.security import sanitize_input"
        files_dict = {
            "utils/security.py": """
            def sanitize_input(val: str) -> str:
                return val.strip()
            """
        }

        result = await stitch_context(
            code=code_under_review,
            file_path="routes.py",
            files_dict=files_dict,
            github_service=None,
            repo_info=None
        )

        assert "### Imported Dependency Context" in result
        assert "File: `utils/security.py`" in result
        assert "Symbol: `sanitize_input`" in result
        assert "def sanitize_input(val: str) -> str:" in result

    @pytest.mark.asyncio
    async def test_stitch_context_syntax_error_handled_gracefully(self) -> None:
        """Stitching on malformed files with syntax errors fails gracefully and returns an empty string."""
        bad_code = "from utils.security import sanitize_input -- this causes a SyntaxError!"
        
        result = await stitch_context(
            code=bad_code,
            file_path="routes.py",
            files_dict={},
            github_service=None,
            repo_info=None
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_stitch_context_respects_max_limit(self) -> None:
        """Stitching stops after processing top-3 dependencies to control token budget."""
        code_with_many_imports = """
        from dep1 import sym1
        from dep2 import sym2
        from dep3 import sym3
        from dep4 import sym4
        """
        files_dict = {
            "dep1.py": "def sym1(): pass",
            "dep2.py": "def sym2(): pass",
            "dep3.py": "def sym3(): pass",
            "dep4.py": "def sym4(): pass",
        }

        result = await stitch_context(
            code=code_with_many_imports,
            file_path="routes.py",
            files_dict=files_dict,
            github_service=None,
            repo_info=None
        )

        # Should match exactly 3 formatted dependency blocks, not 4
        assert result.count("### Imported Dependency Context") == 3