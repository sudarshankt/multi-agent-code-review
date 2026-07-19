from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _stable_dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_prompt_hash(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(_stable_dumps(part).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def cache_path(cache_dir: str | Path, namespace: str, key: str) -> Path:
    base = Path(cache_dir) / namespace
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{key}.json"


def read_cache(cache_dir: str | Path, namespace: str, key: str) -> dict[str, Any] | None:
    path = cache_path(cache_dir, namespace, key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def write_cache(cache_dir: str | Path, namespace: str, key: str, payload: dict[str, Any]) -> None:
    path = cache_path(cache_dir, namespace, key)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
