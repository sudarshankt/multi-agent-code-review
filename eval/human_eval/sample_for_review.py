from __future__ import annotations

import csv
from pathlib import Path


def sample_for_review(output_csv: str | Path | None = None, n: int = 20) -> Path:
    """Create a placeholder review template CSV with sample rows."""
    output_path = Path(output_csv or "eval/human_eval/review_template.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["patch_id", "agent", "pass", "notes"])
        for idx in range(n):
            writer.writerow([f"patch_{idx+1}", "security", "", ""])

    return output_path
