"""Unified LLM service backed by langchain_anthropic.ChatAnthropic.

Notes / spec compliance:
- DO NOT pass `http_async_client` to ChatAnthropic — it is not supported (bug #2).
- Enterprise SSL is handled purely via env vars, and only when SSL_CERT_FILE is
  configured. Public Anthropic usage needs none of this.
- `_extract_json` robustly parses JSON that the model wraps in markdown fences
  (bug #15).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from src.core.config import Settings, get_settings
from src.core.exceptions import LLMError
from src.core.logging import get_logger

logger = get_logger(__name__)


def _configure_ssl_env(cert_file: str | None) -> None:
    """Point common SSL env vars at a custom CA bundle, if provided.

    Only applied when a cert file is explicitly configured (enterprise gateway).
    """
    if not cert_file:
        return
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        os.environ.setdefault(var, cert_file)


# Apply at import time using current settings (no-op for public providers).
_configure_ssl_env(get_settings().llm.ssl_cert_file)


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _find_balanced(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the first balanced {...} or [...] substring, or None."""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_json(text: str) -> Any:
    """Best-effort extraction of a JSON value from an LLM response.

    Order: fenced block -> whole text -> first balanced [..] or {..} -> [].
    Always returns a parsed value; falls back to an empty list.
    """
    if not text:
        return []

    candidates: list[str] = []

    for m in _FENCE_RE.finditer(text):
        candidates.append(m.group(1).strip())

    candidates.append(text.strip())

    # First balanced [..] or {..}, ordered by whichever opener appears first.
    arr_pos = text.find("[")
    obj_pos = text.find("{")
    openers: list[tuple[str, str]] = []
    if arr_pos != -1 and (obj_pos == -1 or arr_pos < obj_pos):
        openers = [("[", "]"), ("{", "}")]
    elif obj_pos != -1:
        openers = [("{", "}"), ("[", "]")]
    for open_ch, close_ch in openers:
        cand = _find_balanced(text, open_ch, close_ch)
        if cand:
            candidates.append(cand)

    for cand in candidates:
        if not cand:
            continue
        try:
            parsed = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, (list, dict)):
            return parsed

    logger.warning(
        "llm_json_parse_failed",
        response_chars=len(text),
        head=text[:300],
        tail=text[-300:] if len(text) > 300 else "",
    )
    return []


class LLMService:
    """Thin async wrapper around ChatAnthropic."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        _configure_ssl_env(self.settings.llm.ssl_cert_file)
        self._model = None  # lazy

    def _build_model(self):
        from langchain_anthropic import ChatAnthropic
        from langchain_core.rate_limiters import InMemoryRateLimiter

        llm = self.settings.llm
        kwargs: dict[str, Any] = {
            "model": llm.primary_model,
            "temperature": 0,
            "max_tokens": llm.max_tokens,
            "timeout": llm.timeout,
            "rate_limiter": InMemoryRateLimiter(
                requests_per_second=llm.requests_per_second
            ),
        }
        if llm.api_key:
            kwargs["api_key"] = llm.api_key
        if llm.base_url:
            kwargs["base_url"] = llm.base_url
        # NOTE: deliberately NOT passing http_async_client (bug #2).
        return ChatAnthropic(**kwargs)

    @property
    def model(self):
        if self._model is None:
            self._model = self._build_model()
        return self._model

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Return the raw text content of a single completion."""
        messages: list[tuple[str, str]] = []
        if system:
            messages.append(("system", system))
        messages.append(("human", prompt))
        try:
            response = await self.model.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001 - normalise to domain error
            raise LLMError(f"LLM completion failed: {exc}", detail=exc) from exc

        content = response.content
        if isinstance(content, list):
            # Anthropic may return a list of content blocks.
            parts = [
                blk.get("text", "") if isinstance(blk, dict) else str(blk)
                for blk in content
            ]
            return "".join(parts)
        return str(content)

    async def complete_json(self, prompt: str, *, system: str | None = None) -> Any:
        """Completion whose text is parsed as JSON (markdown-fence tolerant)."""
        text = await self.complete(prompt, system=system)
        if not isinstance(text, str):
            return []
        return _extract_json(text)


_default_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _default_service
    if _default_service is None:
        _default_service = LLMService()
    return _default_service
