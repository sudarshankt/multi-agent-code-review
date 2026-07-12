"""Graph-Based Context Stitcher.

Parses Python AST to extract local module dependencies, fetches the external code,
and extracts only the exact imported function/class definitions to inject as LLM context.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from typing import Any, NamedTuple

from src.core.logging import get_logger

logger = get_logger(__name__)


class ImportedSymbol(NamedTuple):
    module_path: str   # e.g., "utils.security"
    symbol_name: str   # e.g., "sanitize_input"


class ImportVisitor(ast.NodeVisitor):
    """AST Visitor that identifies all local relative and absolute imports."""

    def __init__(self, current_file: str) -> None:
        self.current_file = current_file
        self.imports: list[ImportedSymbol] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not node.module:
            return

        # Filter out standard libraries or obvious third-party modules
        # A simple heuristic: check if module starts with common third-party names
        ignored_prefixes = ("os", "sys", "json", "asyncio", "django", "flask", "fastapi", "sqlalchemy", "pydantic")
        if node.module.startswith(ignored_prefixes):
            return

        # Record all imported symbols from this local module
        for alias in node.names:
            self.imports.append(
                ImportedSymbol(
                    module_path=node.module,
                    symbol_name=alias.name
                )
            )
        self.generic_visit(node)


class SymbolExtractor(ast.NodeVisitor):
    """AST Visitor that extracts the raw source code of a specific function or class."""

    def __init__(self, target_symbol: str, raw_source: str) -> None:
        self.target_symbol = target_symbol
        self.raw_source = raw_source
        self.extracted_source: str | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == self.target_symbol:
            self.extracted_source = ast.get_source_segment(self.raw_source, node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node.name == self.target_symbol:
            self.extracted_source = ast.get_source_segment(self.raw_source, node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node.name == self.target_symbol:
            self.extracted_source = ast.get_source_segment(self.raw_source, node)
        self.generic_visit(node)


def module_to_file_path(module_path: str) -> str:
    """Converts a module path like 'utils.security' to 'utils/security.py'."""
    return module_path.replace(".", "/") + ".py"


async def fetch_file_content(
    file_path: str,
    files_dict: dict[str, str],
    github_service: Any | None,
    repo_info: dict[str, Any] | None,
    cache: dict[str, str]
) -> str | None:
    """Retrieves file content from PR files_dict, the cache, or falls back to GitHub API."""
    # 1. Check if the file is already in the PR changes
    if file_path in files_dict:
        return files_dict[file_path]

    # 2. Check the memory cache
    if file_path in cache:
        return cache[file_path]

    # 3. Fallback to GitHub REST API if service is available
    if github_service and repo_info:
        try:
            owner = repo_info.get("owner")
            repo = repo_info.get("repo")
            ref = repo_info.get("ref", "main")
            
            logger.debug("Fetching dependency file from GitHub: %s", file_path)
            content = await github_service.get_file_content(owner, repo, file_path, ref)
            if content:
                cache[file_path] = content
                return content
        except Exception as e:
            logger.warning("Failed to fetch %s from GitHub API: %s", file_path, e)

    return None


async def stitch_context(
    code: str,
    file_path: str,
    files_dict: dict[str, str],
    github_service: Any | None = None,
    repo_info: dict[str, Any] | None = None,
    transient_cache: dict[str, str] | None = None
) -> str:
    """Parses local imports, extracts their definitions, and structures context as markdown."""
    cache = transient_cache if transient_cache is not None else {}
    
    try:
        tree = ast.parse(textwrap.dedent(code), filename=file_path)
    except SyntaxError:
        return ""  # Fail gracefully on syntax errors

    # 1. Identify all imports
    visitor = ImportVisitor(current_file=file_path)
    visitor.visit(tree)

    stitched_blocks = []
    # Strict limit to prevent latency/token explosions
    max_dependency_fetches = 3 
    fetched_count = 0

    for imp in visitor.imports:
        if fetched_count >= max_dependency_fetches:
            break

        dep_file_path = module_to_file_path(imp.module_path)
        dep_code = await fetch_file_content(dep_file_path, files_dict, github_service, repo_info, cache)
        
        if not dep_code:
            continue

        # 2. Extract the specific symbol (function/class) from the dependency file
        try:
            dedented_dep = textwrap.dedent(dep_code)
            dep_tree = ast.parse(dedented_dep, filename=dep_file_path)
            extractor = SymbolExtractor(target_symbol=imp.symbol_name, raw_source=dedented_dep)
            extractor.visit(dep_tree)
            
            if extractor.extracted_source:
                block = (
                    f"### Imported Dependency Context\n"
                    f"File: `{dep_file_path}`\n"
                    f"Symbol: `{imp.symbol_name}`\n"
                    f"```python\n"
                    f"{extractor.extracted_source.strip()}\n"
                    f"```"
                )
                stitched_blocks.append(block)
                fetched_count += 1
        except Exception as e:
            logger.debug("Failed extracting symbol %s from %s: %s", imp.symbol_name, dep_file_path, e)

    return "\n\n".join(stitched_blocks)