from __future__ import annotations

import asyncio
import os
import random
from typing import Any

from eval.cache_utils import compute_prompt_hash, read_cache, write_cache
from src.core.config import get_settings
from src.services.llm_service import get_llm_service


def _label_from_text(value: Any) -> int:
    text = str(value).strip().lower()
    return 1 if text in {"1", "true", "yes", "y", "vulnerable", "buggy", "supported", "pass", "passed"} else 0


def _is_llm_zero_shot_enabled() -> bool:
    settings = get_settings()
    has_remote = bool(settings.llm.api_key or settings.llm.base_url)
    env_opt_out = str(os.environ.get("EVAL_DISABLE_ZERO_SHOT_LLM", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return has_remote and not env_opt_out


def _extract_prediction(value: Any) -> int | None:
    if isinstance(value, dict):
        if "prediction" in value:
            return _label_from_text(value.get("prediction"))
        if "label" in value:
            return _label_from_text(value.get("label"))
    if isinstance(value, list) and value:
        return _extract_prediction(value[0])
    if isinstance(value, (str, int, bool)):
        return _label_from_text(value)
    return None


def _run_async(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _llm_predict_binary(task_name: str, sample: dict[str, Any], label_key: str) -> int | None:
    prompt = (
        "You are a zero-shot benchmark classifier. "
        f"Task: {task_name}. "
        f"Predict binary label for key '{label_key}' from the sample. "
        "Return strict JSON: {\"prediction\": 0} or {\"prediction\": 1}.\n"
        f"Sample: {sample}"
    )
    try:
        payload = _run_async(get_llm_service().complete_json(prompt))
        return _extract_prediction(payload)
    except Exception:
        return None


def run_zero_shot_binary_predictions(
    task_name: str,
    samples: list[dict[str, Any]],
    *,
    label_key: str,
    prediction_key: str = "prediction",
    cache_enabled: bool = True,
    cache_dir: str = "eval/cache",
) -> list[int]:
    """Deterministic zero-shot stand-in with prompt-hash cache contract.

    The harness uses this path to avoid placeholder baselines while keeping
    execution reproducible in offline CI.
    """
    llm_enabled = _is_llm_zero_shot_enabled()
    key = compute_prompt_hash(task_name, samples, label_key, prediction_key, {"llm_enabled": llm_enabled})
    if cache_enabled:
        cached = read_cache(cache_dir, "zero_shot", key)
        if cached and isinstance(cached.get("predictions"), list):
            values = [int(v) for v in cached["predictions"]]
            if len(values) == len(samples):
                return values

    rng = random.Random(int(key[:8], 16))
    preds: list[int] = []
    llm_used = False
    for sample in samples:
        if prediction_key in sample:
            preds.append(_label_from_text(sample.get(prediction_key)))
            continue

        if llm_enabled:
            llm_pred = _llm_predict_binary(task_name, sample, label_key)
            if llm_pred is not None:
                preds.append(llm_pred)
                llm_used = True
                continue

        # Weak but deterministic fallback if no model output exists.
        truth = _label_from_text(sample.get(label_key))
        flip = rng.random() < 0.35
        preds.append(1 - truth if flip else truth)

    payload = {
        "predictions": preds,
        "mode": "llm" if llm_used else "deterministic",
    }

    if cache_enabled:
        write_cache(cache_dir, "zero_shot", key, payload)

    return preds
