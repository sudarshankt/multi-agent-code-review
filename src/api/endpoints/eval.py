"""Serves the latest evaluation matrices produced by eval/finding_eval, eval/fix_eval, and eval/e2e_eval.

Also exposes endpoints to trigger a fresh eval run in the background (as a
subprocess invoking the same `python -m eval.<type>_eval.run_eval` entry
points used from the CLI) and to poll its status, so the dashboard can kick
off an eval and show the resulting report once it completes.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException

from src.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LATEST_RESULT_PATH = _REPO_ROOT / "eval" / "results" / "finding" / "latest.json"
_LATEST_FIX_RESULT_PATH = _REPO_ROOT / "eval" / "results" / "fix" / "latest.json"
_LATEST_E2E_RESULT_PATH = _REPO_ROOT / "eval" / "results" / "e2e" / "latest.json"

EvalType = Literal["finding", "fix", "e2e"]

_EVAL_MODULES: dict[EvalType, str] = {
    "finding": "eval.finding_eval.run_eval",
    "fix": "eval.fix_eval.run_eval",
    "e2e": "eval.e2e_eval.run_eval",
}

_RUN_TIMEOUT_SECS = 600

# In-memory status per eval type. A single process instance is assumed
# (mirrors the in-memory review store used elsewhere in this API).
_run_status: dict[EvalType, dict] = {
    eval_type: {"status": "idle", "started_at": None, "finished_at": None, "error": None, "log_tail": ""}
    for eval_type in _EVAL_MODULES
}


def _resolve_venv_python() -> str:
    """Return the venv Python executable so the subprocess has the project's deps."""
    venv_python = Path(sys.prefix) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if venv_python.is_file():
        return str(venv_python)
    if Path(sys.executable).is_file():
        return sys.executable
    return "python"


async def _run_eval_subprocess(eval_type: EvalType) -> None:
    state = _run_status[eval_type]
    state.update(status="running", started_at=time.time(), finished_at=None, error=None, log_tail="")

    python_exe = _resolve_venv_python()
    module = _EVAL_MODULES[eval_type]
    cmd = [python_exe, "-m", module]

    logger.info("eval_run_start", eval_type=eval_type, cmd=cmd)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_REPO_ROOT,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=_RUN_TIMEOUT_SECS)
        combined = (stdout_b + stderr_b).decode(errors="replace")
        state["log_tail"] = combined[-4000:]

        if proc.returncode == 0:
            state["status"] = "completed"
            logger.info("eval_run_complete", eval_type=eval_type)
        else:
            state["status"] = "failed"
            state["error"] = f"exit code {proc.returncode}"
            logger.warning("eval_run_failed", eval_type=eval_type, returncode=proc.returncode)
    except asyncio.TimeoutError:
        state["status"] = "failed"
        state["error"] = f"timed out after {_RUN_TIMEOUT_SECS}s"
        logger.warning("eval_run_timeout", eval_type=eval_type)
    except Exception as exc:  # noqa: BLE001 - surface any launch failure to the UI
        state["status"] = "failed"
        state["error"] = str(exc)
        logger.error("eval_run_error", eval_type=eval_type, error=str(exc))
    finally:
        state["finished_at"] = time.time()


@router.post("/run/{eval_type}", status_code=202)
async def trigger_eval_run(eval_type: EvalType) -> dict:
    """Kick off `python -m eval.<eval_type>_eval.run_eval` in the background."""
    if _run_status[eval_type]["status"] == "running":
        raise HTTPException(status_code=409, detail=f"{eval_type} eval is already running")

    asyncio.create_task(_run_eval_subprocess(eval_type))
    return {"eval_type": eval_type, "status": "running"}


@router.get("/run/{eval_type}/status")
async def get_eval_run_status(eval_type: EvalType) -> dict:
    return {"eval_type": eval_type, **_run_status[eval_type]}


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
