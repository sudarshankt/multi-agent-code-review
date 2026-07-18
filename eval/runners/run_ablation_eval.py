from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def run_ablation_eval(output_dir: str | Path | None = None) -> dict[str, Any]:
    """Create a sample ablation evaluation result payload."""
    payload = {
        "benchmark": "Ablation baseline",
        "agent": "all",
        "n": 100,
        "metrics": {"f1": 0.58},
        "baseline_zero_shot": {"f1": 0.58},
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir or "results")
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "ablation_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
