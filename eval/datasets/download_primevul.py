from __future__ import annotations

import subprocess
from pathlib import Path


def download_primevul(output_dir: str | Path | None = None) -> Path:
    """Clone the PrimeVul repository into the local dataset directory when possible."""
    target_dir = Path(output_dir or "eval/datasets/data/primevul")
    target_dir.mkdir(parents=True, exist_ok=True)

    if not (target_dir / ".git").exists():
        repo_url = "https://github.com/DLVulDet/PrimeVul.git"
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            (target_dir / ".placeholder").write_text("PrimeVul dataset placeholder", encoding="utf-8")
    return target_dir
