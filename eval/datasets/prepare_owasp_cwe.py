from __future__ import annotations

import json
import shutil
from pathlib import Path


def prepare_owasp_cwe(output_dir: str | Path | None = None) -> Path:
    """Copy the repository's OWASP/CWE knowledge base into a local evaluation dataset directory."""
    target_dir = Path(output_dir or "eval/datasets/data/owasp_cwe")
    target_dir.mkdir(parents=True, exist_ok=True)

    source_dir = Path(__file__).resolve().parents[1] / ".." / "knowledge_base" / "owasp"
    if source_dir.exists():
        for path in source_dir.glob("*.json"):
            shutil.copy2(path, target_dir / path.name)

    if not any(target_dir.iterdir()):
        (target_dir / ".placeholder").write_text("OWASP/CWE dataset placeholder", encoding="utf-8")
    return target_dir
