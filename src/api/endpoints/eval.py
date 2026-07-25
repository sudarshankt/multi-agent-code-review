"""Serves the latest evaluation matrices produced by eval/finding_eval, eval/fix_eval, and eval/e2e_eval."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LATEST_RESULT_PATH = _REPO_ROOT / "eval" / "results" / "finding" / "latest.json"
_LATEST_FIX_RESULT_PATH = _REPO_ROOT / "eval" / "results" / "fix" / "latest.json"
_LATEST_E2E_RESULT_PATH = _REPO_ROOT / "eval" / "results" / "e2e" / "latest.json"


@router.get("/latest")
async def get_latest_eval() -> dict:
    """Return the most recently generated finding-agent evaluation report."""
    if not _LATEST_RESULT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No eval report found. Run `python -m eval.finding_eval.run_eval` first.",
        )
    return json.loads(_LATEST_RESULT_PATH.read_text(encoding="utf-8"))


@router.get("/latest-fix")
async def get_latest_fix_eval() -> dict:
    """Return the most recently generated fix-agent LLM-as-judge report."""
    if not _LATEST_FIX_RESULT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No fix-eval report found. Run `python -m eval.fix_eval.run_eval` first.",
        )
    return json.loads(_LATEST_FIX_RESULT_PATH.read_text(encoding="utf-8"))


@router.get("/latest-e2e")
async def get_latest_e2e_eval() -> dict:
    """Return the most recently generated end-to-end (finding -> fix) pipeline report."""
    if not _LATEST_E2E_RESULT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No e2e-eval report found. Run `python -m eval.e2e_eval.run_eval` first.",
        )
    return json.loads(_LATEST_E2E_RESULT_PATH.read_text(encoding="utf-8"))
