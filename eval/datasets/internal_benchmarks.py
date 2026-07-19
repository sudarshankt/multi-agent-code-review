from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "supported", "pass", "passed"}


def load_repo_level_bug_samples(path: str | Path = "eval/datasets/data/repo_level_bug_samples.json") -> list[dict[str, Any]]:
    sample_path = Path(path)
    if sample_path.exists():
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

    return [
        {"repo": "demo/service-a", "label": 1, "prediction": 1},
        {"repo": "demo/service-b", "label": 0, "prediction": 0},
        {"repo": "demo/service-c", "label": 1, "prediction": 0},
        {"repo": "demo/service-d", "label": 0, "prediction": 0},
    ]


def load_codexglue_security_samples(path: str | Path = "eval/datasets/data/codexglue_security_samples.json") -> list[dict[str, Any]]:
    sample_path = Path(path)
    if sample_path.exists():
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

    return [
        {"sample_id": "cxg-1", "label": 1, "prediction": 1},
        {"sample_id": "cxg-2", "label": 0, "prediction": 0},
        {"sample_id": "cxg-3", "label": 1, "prediction": 0},
        {"sample_id": "cxg-4", "label": 0, "prediction": 1},
    ]


def load_cyberseceval_samples(path: str | Path = "eval/datasets/data/cyberseceval_samples.json") -> list[dict[str, Any]]:
    sample_path = Path(path)
    if sample_path.exists():
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

    return [
        {"scenario_id": "cse-1", "secure_assistance": True},
        {"scenario_id": "cse-2", "secure_assistance": False},
        {"scenario_id": "cse-3", "secure_assistance": True},
        {"scenario_id": "cse-4", "secure_assistance": True},
    ]


def load_patcheval_samples(path: str | Path = "eval/datasets/data/patcheval_samples.json") -> list[dict[str, Any]]:
    sample_path = Path(path)
    if sample_path.exists():
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

    return [
        {"patch_id": "pe-1", "correct": True},
        {"patch_id": "pe-2", "correct": False},
        {"patch_id": "pe-3", "correct": True},
        {"patch_id": "pe-4", "correct": True},
    ]


def load_defects4j_patch_samples(path: str | Path = "eval/datasets/data/defects4j_patch_samples.json") -> list[dict[str, Any]]:
    sample_path = Path(path)
    if sample_path.exists():
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

    return [
        {"patch_id": "d4j-1", "tests_pass": True, "touched_test_files": False},
        {"patch_id": "d4j-2", "tests_pass": False, "touched_test_files": False},
        {"patch_id": "d4j-3", "tests_pass": True, "touched_test_files": True},
        {"patch_id": "d4j-4", "tests_pass": True, "touched_test_files": False},
    ]


def load_citation_review(path: str | Path = "eval/human_eval/citation_review.csv") -> list[dict[str, Any]]:
    review_path = Path(path)
    if review_path.exists():
        with review_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [row for row in reader if isinstance(row, dict)]
        if rows:
            return rows

    return [
        {"claim_id": "c1", "supported": "yes", "notes": "Default fallback row"},
        {"claim_id": "c2", "supported": "no", "notes": "Default fallback row"},
    ]


def load_secbench_patch_samples(path: str | Path = "eval/datasets/data/secbench_patch_samples.json") -> list[dict[str, Any]]:
    sample_path = Path(path)
    if sample_path.exists():
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

    return [
        {"case_id": "sb-1", "patch_pass": True, "poc_reproduced": True},
        {"case_id": "sb-2", "patch_pass": False, "poc_reproduced": False},
        {"case_id": "sb-3", "patch_pass": True, "poc_reproduced": True},
        {"case_id": "sb-4", "patch_pass": False, "poc_reproduced": False},
    ]


def load_performance_samples(path: str | Path = "eval/datasets/data/performance_samples.json") -> list[dict[str, Any]]:
    sample_path = Path(path)
    if sample_path.exists():
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

    return [
        {"sample_id": "perf-1", "hotspot": True, "prediction": True},
        {"sample_id": "perf-2", "hotspot": False, "prediction": False},
        {"sample_id": "perf-3", "hotspot": True, "prediction": False},
        {"sample_id": "perf-4", "hotspot": False, "prediction": False},
    ]


def summarize_binary_rate(rows: list[dict[str, Any]], key: str) -> tuple[float, int]:
    if not rows:
        return 0.0, 0
    values = [_to_bool(row.get(key, False)) for row in rows]
    return sum(1 for v in values if v) / len(values), len(values)
