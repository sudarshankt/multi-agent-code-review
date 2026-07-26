"""Download / load PatchEval (Wei et al., arXiv:2511.11019, ByteDance/HUST) —
the PRIMARY Patch Generation Agent benchmark, filtered to its Python subset.

Repo verified: https://github.com/bytedance/PatchEval — the CVE metadata
ships directly in the git repo as JSON (no manual step needed for this
part; the 230-CVE runtime-sandbox subset does need Docker, see below):
  patcheval/datasets/input.json           (1,000 CVEs, all metadata)
  patcheval/datasets/patcheval_dataset.json

Verified language distribution in input.json: Python=404, Go=296,
JavaScript=300 — filter on the `programming_language` field, exactly as
shown below.

Each entry (verified structure): {"cve_id", "cwe_id": [...], "cve_description",
"cwe_info": {...}, "repo", "patch_url": [...], "programming_language",
"vul_func": [{"id","commit","file_path","start_line","end_line","snippet"}]}

NOTE: only 230 of the 1,000 CVEs have runtime sandbox environments for full
PoC + functionality-test verification (Docker required, ~500GB disk per the
repo's README). The rest support the "Patch Generation with Location
Oracle" setting (no sandbox needed) — patch correctness there has to be
judged some other way (e.g. static diff comparison, or human review — see
eval/human_eval/). Check which of your sampled Python CVEs have sandbox
support before assuming automated pass/fail is available.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from eval.common import REPO_ROOT, load_config

REPO_URL = "https://github.com/bytedance/PatchEval.git"
DATA_REL_PATHS = (
    "patcheval/datasets/input.json",             # older/public metadata file
    "patcheval/datasets/patcheval_verified.json",  # current upstream file
)


def download(dest: Path | None = None) -> Path:
    cfg = load_config()
    dest = dest or REPO_ROOT / cfg["paths"]["dataset_dir"] / "patcheval"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not dest.exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(dest)], check=True)
        print(
            "[patcheval] cloned metadata. For the 230 CVEs with runtime "
            "sandbox verification, follow the repo's Docker setup "
            "(scripts/download_images.py, ~500GB disk) separately."
        )
    else:
        print(f"[patcheval] already present at {dest}")
    return dest


def load_python_subset(sample_n: int | None = None, dest: Path | None = None) -> list[dict]:
    cfg = load_config()
    dest = dest or REPO_ROOT / cfg["paths"]["dataset_dir"] / "patcheval"
    data_file = next((dest / p for p in DATA_REL_PATHS if (dest / p).exists()), None)
    if data_file is None:
        raise FileNotFoundError(
            "No supported PatchEval dataset file found under "
            f"{dest / 'patcheval/datasets'} (looked for: {', '.join(DATA_REL_PATHS)}). "
            "Run `python -m eval.datasets.download_patcheval` first."
        )

    with open(data_file) as f:
        data = json.load(f)

    # PatchEval schema uses either `programming_language` (older) or
    # `programing_language` (current verified dataset; typo kept upstream).
    python_entries = [
        d
        for d in data
        if (d.get("programming_language") or d.get("programing_language")) == "Python"
    ]
    n = sample_n if sample_n is not None else cfg["sample_sizes"].get("patcheval_python_n")
    if n is not None and n < len(python_entries):
        python_entries = python_entries[:n]
    return python_entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=str, default=None)
    args = parser.parse_args()
    d = download(Path(args.dest) if args.dest else None)
    try:
        py = load_python_subset(dest=d)
        print(f"[patcheval] {len(py)} Python CVEs available out of the 1,000 total")
    except FileNotFoundError as e:
        print(e)
