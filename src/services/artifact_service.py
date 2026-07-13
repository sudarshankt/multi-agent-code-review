"""Persist generated review artifacts such as fixed code snapshots for inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.models.finding import FixResult


def persist_generated_artifacts(
    review_id: str,
    fix_results: list[FixResult],
    output_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Write successful fix outputs to a review-scoped directory.

    The artifacts are stored under a review-specific folder so they can be
    checked in or inspected later without affecting the live source tree.
    """
    root = Path(output_dir or "results/generated")
    review_dir = root / review_id
    review_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    for result in fix_results:
        if not result.success or not result.fixed_code:
            continue

        artifact_path = review_dir / result.file_path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(result.fixed_code, encoding="utf-8")

        result.artifact_path = str(artifact_path)
        manifest.append(
            {
                "file_path": result.file_path,
                "artifact_path": str(artifact_path),
                "commit_sha": result.commit_sha,
                "commit_message": result.commit_message,
            }
        )

    return manifest
