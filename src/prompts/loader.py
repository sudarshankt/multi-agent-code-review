"""Jinja2 prompt-template loader."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@lru_cache
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )


def render(template_name: str, **context: object) -> str:
    template = _env().get_template(template_name)
    return template.render(**context)
