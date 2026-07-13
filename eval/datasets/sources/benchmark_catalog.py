from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_dataset_root(root: str | Path | None = None) -> Path:
    """Resolve the local dataset root, falling back to eval/datasets/data."""
    if root:
        return Path(root).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data"


def list_available_benchmarks(root: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Inspect a local dataset root for known benchmark directories."""
    dataset_root = resolve_dataset_root(root)
    dataset_root.mkdir(parents=True, exist_ok=True)
    return {
        "primevul": {"path": dataset_root / "primevul", "exists": (dataset_root / "primevul").exists()},
        "secbench": {"path": dataset_root / "secbench", "exists": (dataset_root / "secbench").exists()},
        "defects4j": {"path": dataset_root / "defects4j", "exists": (dataset_root / "defects4j").exists()},
        "owasp_cwe": {"path": dataset_root / "owasp_cwe", "exists": (dataset_root / "owasp_cwe").exists()},
    }
