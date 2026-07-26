# Purpose: Covers review preflight behavior, including skipping oversized PRs before the analysis pipeline starts.

from __future__ import annotations

import pytest

from src.api.endpoints import review as review_module
from src.api.schemas.review import CreateReviewRequest
from src.core.config import get_settings
from src.models.review import ReviewStatus


@pytest.mark.asyncio
async def test_create_review_skips_large_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_FILES_PER_PR", "2")
    get_settings.cache_clear()

    class FakeGitHubService:
        async def __aenter__(self) -> "FakeGitHubService":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict[str, object]]:
            return [
                {"filename": "app/main.py", "status": "modified"},
                {"filename": "app/utils.py", "status": "modified"},
                {"filename": "app/extra.py", "status": "modified"},
            ]

    monkeypatch.setattr(review_module, "GitHubService", FakeGitHubService)

    response = await review_module.create_review(
        CreateReviewRequest(owner="octo", repo="demo", pr_number=42)
    )

    assert response.status == ReviewStatus.SKIPPED
    assert response.total_findings == 0
