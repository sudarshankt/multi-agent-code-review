"""GitHub REST API client (public api.github.com by default).

Uses httpx.AsyncClient with Bearer-token auth. SSL verification uses the system
trust store by default; set GITHUB_CA_BUNDLE for an enterprise CA.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from src.core.config import Settings, get_settings
from src.core.constants import SOURCE_EXTENSIONS
from src.core.exceptions import GitHubAPIError, GitHubRateLimitError
from src.core.logging import get_logger
from src.models.review import PRInfo

logger = get_logger(__name__)

API_VERSION = "2022-11-28"


def _is_source_file(path: str) -> bool:
    return path.endswith(SOURCE_EXTENSIONS)


class GitHubService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        gh = self.settings.github
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if gh.token:
            headers["Authorization"] = f"Bearer {gh.token}"
        self._client = httpx.AsyncClient(
            base_url=gh.base_url,
            headers=headers,
            verify=gh.ca_bundle or True,
            timeout=30.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GitHubService:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def _get(self, url: str, *, accept: str | None = None) -> httpx.Response:
        headers = {"Accept": accept} if accept else None
        try:
            resp = await self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise GitHubAPIError(f"GitHub request failed: {exc}", detail=exc) from exc
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise GitHubRateLimitError("GitHub rate limit exceeded", detail=resp.text)
        if resp.status_code >= 400:
            raise GitHubAPIError(
                f"GitHub API {resp.status_code} for {url}", detail=resp.text
            )
        return resp

    async def get_pr(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        resp = await self._get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        return resp.json()

    async def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        resp = await self._get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            accept="application/vnd.github.diff",
        )
        return resp.text

    async def get_pr_files(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = await self._get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files"
                f"?per_page=100&page={page}"
            )
            batch = resp.json()
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return files

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str | None:
        try:
            resp = await self._get(
                f"/repos/{owner}/{repo}/contents/{path}?ref={ref}"
            )
        except GitHubAPIError:
            logger.warning("get_file_content_failed", path=path, ref=ref)
            return None
        data = resp.json()
        if isinstance(data, dict) and data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return None

    def _build_pr_info(self, owner: str, repo: str, pr: dict[str, Any]) -> PRInfo:
        return PRInfo(
            owner=owner,
            repo=repo,
            pr_number=pr["number"],
            title=pr.get("title"),
            author=(pr.get("user") or {}).get("login"),
            head_branch=(pr.get("head") or {}).get("ref"),
            base_branch=(pr.get("base") or {}).get("ref"),
            head_sha=(pr.get("head") or {}).get("sha"),
            html_url=pr.get("html_url"),
        )

    async def fetch_pr_data(
        self, owner: str, repo: str, pr_number: int
    ) -> dict[str, Any]:
        """Combine PR metadata, changed source files, and their content."""
        pr = await self.get_pr(owner, repo, pr_number)
        pr_info = self._build_pr_info(owner, repo, pr)

        changed = await self.get_pr_files(owner, repo, pr_number)
        files: dict[str, str] = {}
        diffs: dict[str, str] = {}
        for entry in changed:
            path = entry.get("filename", "")
            if entry.get("status") == "removed" or not _is_source_file(path):
                continue
            content = await self.get_file_content(
                owner, repo, path, pr_info.head_sha or pr_info.head_branch or "HEAD"
            )
            if content is not None:
                files[path] = content
            patch = entry.get("patch")
            if isinstance(patch, str) and patch.strip():
                diffs[path] = patch

        logger.info(
            "fetched_pr_data",
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            changed=len(changed),
            source_files=len(files),
        )
        return {"pr_info": pr_info, "files": files, "diffs": diffs, "changed_files": changed}
