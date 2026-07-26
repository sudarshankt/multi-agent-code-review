"""Standalone startup launcher for eval_PR.

This module provides one entrypoint to:
1) verify runtime dependencies,
2) load environment variables,
3) initialize configured LLM clients, and
4) launch either the Streamlit GUI or CLI audit flow.

Examples:
  python -m eval_pr.startup doctor
  python -m eval_pr.startup gui --host 0.0.0.0 --port 8501
  python -m eval_pr.startup cli --pr path/to/pr.diff --fixed-output path/to/fixed_code.txt
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def _repo_env_candidates(root: Path) -> list[Path]:
	"""Return .env candidates in priority order."""
	return [
		root / ".env",
		root.parent / ".env",
	]


def _load_environment(root: Path) -> Path | None:
	"""Load .env if present and return loaded file path."""
	from dotenv import load_dotenv

	for candidate in _repo_env_candidates(root):
		if candidate.exists():
			load_dotenv(candidate)
			return candidate
	load_dotenv()
	return None


def _missing_deps() -> list[str]:
	"""Return required import names that are not installed."""
	required = ["dotenv", "streamlit", "anthropic", "openai"]
	missing: list[str] = []
	for name in required:
		if importlib.util.find_spec(name) is None:
			missing.append(name)
	return missing


def _init_clients() -> dict[str, str]:
	"""Initialize configured judge/baseline clients and return status map."""
	from eval_pr.config import (
		BASELINE_MODEL,
		JUDGE_MODEL,
		api_key_configured,
		get_client_for_model,
		get_provider_for_model,
	)

	checks: dict[str, str] = {}

	if not api_key_configured():
		checks["keys"] = "no_api_keys_configured"
		return checks

	for model_label, model_name in (("judge", JUDGE_MODEL), ("baseline", BASELINE_MODEL)):
		provider = get_provider_for_model(model_name)
		client = get_client_for_model(model_name)
		checks[f"{model_label}_provider"] = provider
		checks[f"{model_label}_model"] = model_name
		checks[f"{model_label}_client"] = "ok" if client is not None else "failed"

	return checks


def _run(cmd: list[str], cwd: Path) -> int:
	"""Run a command and return exit code."""
	proc = subprocess.run(cmd, cwd=str(cwd))
	return proc.returncode


def cmd_doctor(root: Path) -> int:
	"""Run local diagnostics for independent module startup."""
	missing = _missing_deps()
	if missing:
		print("[eval_pr] missing dependencies:", ", ".join(missing))
		print("[eval_pr] install with: python -m pip install -r requirements.txt")
		return 1

	env_file = _load_environment(root)
	if env_file:
		print(f"[eval_pr] loaded env: {env_file}")
	else:
		print("[eval_pr] no .env file found (continuing with current environment)")

	checks = _init_clients()
	for key, value in checks.items():
		print(f"[eval_pr] {key}={value}")

	print("[eval_pr] doctor complete")
	return 0


def cmd_gui(root: Path, host: str, port: int) -> int:
	"""Launch Streamlit app with initialized environment."""
	missing = _missing_deps()
	if missing:
		print("[eval_pr] missing dependencies:", ", ".join(missing))
		print("[eval_pr] install with: python -m pip install -r requirements.txt")
		return 1

	env_file = _load_environment(root)
	if env_file:
		print(f"[eval_pr] loaded env: {env_file}")

	checks = _init_clients()
	for key, value in checks.items():
		print(f"[eval_pr] {key}={value}")

	cmd = [
		sys.executable,
		"-m",
		"streamlit",
		"run",
		"eval_pr/gui/app.py",
		"--server.address",
		host,
		"--server.port",
		str(port),
	]
	return _run(cmd, cwd=root)


def cmd_cli(root: Path, pr: str, fixed_output: str, output_dir: str) -> int:
	"""Launch eval_PR CLI flow with initialized environment."""
	missing = _missing_deps()
	# CLI does not require streamlit; keep this strict list for standalone launch parity.
	if missing:
		print("[eval_pr] missing dependencies:", ", ".join(missing))
		print("[eval_pr] install with: python -m pip install -r requirements.txt")
		return 1

	env_file = _load_environment(root)
	if env_file:
		print(f"[eval_pr] loaded env: {env_file}")

	checks = _init_clients()
	for key, value in checks.items():
		print(f"[eval_pr] {key}={value}")

	cmd = [
		sys.executable,
		"-m",
		"eval_pr.run_single_pr",
		"--pr",
		pr,
		"--fixed-output",
		fixed_output,
		"--output-dir",
		output_dir,
	]
	return _run(cmd, cwd=root)


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Standalone launcher for eval_PR")
	sub = parser.add_subparsers(dest="command", required=True)

	sub.add_parser("doctor", help="Validate deps/env/LLM client initialization")

	gui = sub.add_parser("gui", help="Launch Streamlit GUI")
	gui.add_argument("--host", default="0.0.0.0")
	gui.add_argument("--port", type=int, default=8501)

	cli = sub.add_parser("cli", help="Run CLI audit")
	cli.add_argument("--pr", required=True, help="Path to original PR file")
	cli.add_argument("--fixed-output", required=True, help="Path to Fixed Code file")
	cli.add_argument("--output-dir", default="eval_pr_results", help="Output directory")

	return parser


def main() -> None:
	parser = build_parser()
	args = parser.parse_args()

	root = Path(__file__).resolve().parents[1]
	os.chdir(root)

	if args.command == "doctor":
		raise SystemExit(cmd_doctor(root))
	if args.command == "gui":
		raise SystemExit(cmd_gui(root, host=args.host, port=args.port))
	if args.command == "cli":
		raise SystemExit(
			cmd_cli(root, pr=args.pr, fixed_output=args.fixed_output, output_dir=args.output_dir)
		)


if __name__ == "__main__":
	main()
