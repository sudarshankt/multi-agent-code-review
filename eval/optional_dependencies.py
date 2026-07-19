from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
import sys
from typing import Any


def dependency_status(import_name: str, install_spec: str) -> dict[str, Any]:
    """Return dependency availability and optionally auto-install when enabled."""
    auto_install = os.getenv("EVAL_AUTO_INSTALL_OPTIONAL_DEPS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    try:
        importlib.import_module(import_name)
        return {
            "name": import_name,
            "available": True,
            "auto_enabled": True,
            "install_hint": f"pip install {install_spec}",
        }
    except Exception as exc:
        # Some packages can be installed but fail import due optional provider integrations.
        # In that case we still report installed availability with a warning message.
        spec = importlib.util.find_spec(import_name)
        if spec is not None:
            return {
                "name": import_name,
                "available": True,
                "auto_enabled": True,
                "import_warning": str(exc),
                "install_hint": f"pip install {install_spec}",
            }

        if auto_install:
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", install_spec],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                importlib.import_module(import_name)
                return {
                    "name": import_name,
                    "available": True,
                    "auto_enabled": True,
                    "installed_during_run": True,
                    "install_hint": f"pip install {install_spec}",
                }
            except Exception as install_exc:
                pass
                exc = install_exc

        return {
            "name": import_name,
            "available": False,
            "auto_enabled": False,
            "import_error": str(exc),
            "install_hint": f"pip install {install_spec}",
        }


def collect_optional_dependency_status() -> dict[str, dict[str, Any]]:
    """Collect status for optional evaluation dependencies."""
    return {
        "radon": dependency_status("radon", "radon"),
        "ragas": dependency_status("ragas", "ragas"),
    }
