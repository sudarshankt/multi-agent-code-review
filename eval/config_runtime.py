from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class EvalConfig:
    """Runtime configuration used by the evaluation harness."""

    dataset_root: str = "./data"
    primevul_n: int = 100
    secbench_n: int = 50
    defects4j_n: int = 50
    radon_sample_n: int = 20
    ragas_sample_n: int = 20
    cache_dir: str = "./eval/cache"
    cache_enabled: bool = True
    output_dir: str = "./results"


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _parse_yaml_fallback(path: Path) -> dict[str, dict[str, str]]:
    """Best-effort parser for simple nested key/value yaml sections."""
    parsed: dict[str, dict[str, str]] = {}
    section = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if raw_line[0].isspace() and section and ":" in line:
            key, value = line.split(":", 1)
            parsed.setdefault(section, {})[key.strip()] = value.strip()
            continue
        if line.endswith(":"):
            section = line[:-1].strip()
            parsed.setdefault(section, {})
    return parsed


def load_eval_config(path: str | Path = "eval/config.yaml") -> EvalConfig:
    """Load eval config from yaml, with safe defaults for missing keys."""
    cfg_path = Path(path)
    if not cfg_path.exists():
        return EvalConfig()

    config: dict[str, Any]
    try:
        import yaml  # type: ignore[import-not-found]

        parsed = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        config = parsed if isinstance(parsed, dict) else {}
    except Exception:
        config = _parse_yaml_fallback(cfg_path)

    datasets = config.get("datasets", {}) if isinstance(config, dict) else {}
    cache = config.get("cache", {}) if isinstance(config, dict) else {}
    report = config.get("report", {}) if isinstance(config, dict) else {}

    return EvalConfig(
        dataset_root=str(datasets.get("root", "./data")),
        primevul_n=_coerce_int(datasets.get("primevul_n"), 100),
        secbench_n=_coerce_int(datasets.get("secbench_n"), 50),
        defects4j_n=_coerce_int(datasets.get("defects4j_n"), 50),
        radon_sample_n=_coerce_int(datasets.get("radon_sample_n"), 20),
        ragas_sample_n=_coerce_int(datasets.get("ragas_sample_n"), 20),
        cache_dir=str(cache.get("dir", "./eval/cache")),
        cache_enabled=_coerce_bool(cache.get("enabled"), True),
        output_dir=str(report.get("output_dir", "./results")),
    )
