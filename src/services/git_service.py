"""Git write operations via the GitHub REST API (no local clone).

Commit flow (Build_from_Scratch.md section 3):
  1. GET ref            -> HEAD sha
  2. GET commit         -> base tree sha
  3. POST blobs         -> blob shas  (content MUST be base64, bug #3)
  4. POST trees         -> new tree sha
  5. POST commits       -> new commit sha (message contains GENAI=YES, bug #4)
  6. PATCH refs         -> branch points at new commit
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from src.core.config import Settings, get_settings
from src.core.exceptions import GitOperationError
from src.core.logging import get_logger

logger = get_logger(__name__)

API_VERSION = "2022-11-28"
BLOB_MODE = "100644"


class GitService:
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

    async def __aenter__(self) -> GitService:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise GitOperationError(f"Git request failed: {exc}", detail=exc) from exc
        if resp.status_code >= 400:
            raise GitOperationError(
                f"Git API {resp.status_code} for {method} {url}", detail=resp.text
            )
        return resp.json()

    async def commit_fixes(
        self,
        owner: str,
        repo: str,
        branch: str,
        files: dict[str, str],
        message: str,
    ) -> str:
        """Commit a mapping of path -> new content to `branch`. Returns new sha."""
        if not files:
            raise GitOperationError("commit_fixes called with no files")

        base = f"/repos/{owner}/{repo}/git"

        # 1. HEAD sha of the branch
        ref = await self._request("GET", f"{base}/ref/heads/{branch}")
        head_sha = ref["object"]["sha"]

        # 2. base tree sha
        commit = await self._request("GET", f"{base}/commits/{head_sha}")
        base_tree_sha = commit["tree"]["sha"]

        # 3. blobs (base64-encoded content -- required, bug #3)
        tree_entries: list[dict[str, Any]] = []
        for path, content in files.items():
            b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
            blob = await self._request(
                "POST",
                f"{base}/blobs",
                json={"content": b64, "encoding": "base64"},
            )
            tree_entries.append(
                {
                    "path": path,
                    "mode": BLOB_MODE,
                    "type": "blob",
                    "sha": blob["sha"],
                }
            )

        # 4. new tree
        tree = await self._request(
            "POST",
            f"{base}/trees",
            json={"base_tree": base_tree_sha, "tree": tree_entries},
        )

        # 5. new commit (message must contain GENAI=YES, bug #4)
        new_commit = await self._request(
            "POST",
            f"{base}/commits",
            json={
                "message": message,
                "tree": tree["sha"],
                "parents": [head_sha],
            },
        )
        new_sha = new_commit["sha"]

        # 6. move the branch ref
        await self._request(
            "PATCH",
            f"{base}/refs/heads/{branch}",
            json={"sha": new_sha, "force": False},
        )

        logger.info(
            "committed_fixes",
            owner=owner,
            repo=repo,
            branch=branch,
            files=len(files),
            commit_sha=new_sha,
        )
        return new_sha
