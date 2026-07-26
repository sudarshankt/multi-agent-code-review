"""Download / load SeCodePLT (Nie et al., arXiv:2410.11096, NeurIPS 2025) —
the PRIMARY Security Agent benchmark (Python-native).

Repo verified: https://github.com/ucsb-mlsec/SecCodePLT — the core dataset
ships directly in the git repo as JSON (no HuggingFace / manual step
needed):
  virtue_code_eval/data/safety/secodeplt/data.json   (1,411 samples, 28 CWEs)

Verified this core dataset is Python (10/10 sampled entries used Python
`def` syntax) — the C/C++/Java coverage lives in a SEPARATE dataset,
SeCodePLT-Juliet (built on the classic NIST Juliet Test Suite), which we
don't need and don't pull in here.

Each entry:
  {
    "CWE_ID": str,
    "task_description": {"function_name", "description", "security_policy",
                          "context", "arguments", "return", "raise"},
    "ground_truth": {"code_before": str, "vulnerable_code": str, "patched_code": str},
    "unittest": ..., "install_requires": [...], "rule": ..., "index": int
  }
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from eval.common import REPO_ROOT, load_config

REPO_URL = "https://github.com/ucsb-mlsec/SecCodePLT.git"
DATA_REL_PATH = "virtue_code_eval/data/safety/secodeplt/data.json"


def download(dest: Path | None = None) -> Path:
    cfg = load_config()
    dest = dest or REPO_ROOT / cfg["paths"]["dataset_dir"] / "seccodeplt"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not dest.exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(dest)], check=True)
    else:
        print(f"[seccodeplt] already present at {dest}")

    data_file = dest / DATA_REL_PATH
    if not data_file.exists():
        print(
            f"[seccodeplt] WARNING: expected data file not found at {data_file}. "
            "The repo's internal layout may have changed since this script was "
            "written — check virtue_code_eval/data/safety/ in the cloned repo."
        )
    return dest


def load_samples(sample_n: int | None = None, dest: Path | None = None, indices: list[int] | None = None) -> list[dict]:
    """If `indices` is given, returns exactly those samples (matched on
    each sample's own "index" field), in the order given — ignoring
    sample_n. Used by eval.shared_cases to guarantee Layer A and Layer B/C
    score the identical underlying examples. Raises if any requested index
    isn't found, since a silent partial match would make cross-layer
    comparison misleading.
    """
    cfg = load_config()
    dest = dest or REPO_ROOT / cfg["paths"]["dataset_dir"] / "seccodeplt"
    data_file = dest / DATA_REL_PATH
    if not data_file.exists():
        raise FileNotFoundError(
            f"{data_file} not found. Run `python -m eval.datasets.download_seccodeplt` first."
        )

    with open(data_file) as f:
        data = json.load(f)

    if indices is not None:
        by_index = {s["index"]: s for s in data}
        missing = [i for i in indices if i not in by_index]
        if missing:
            raise ValueError(f"SecCodePLT indices not found: {missing}")
        return [by_index[i] for i in indices]

    n = sample_n if sample_n is not None else cfg["sample_sizes"].get("seccodeplt_n")
    if n is not None and n < len(data):
        data = data[:n]
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=str, default=None)
    args = parser.parse_args()
    d = download(Path(args.dest) if args.dest else None)
    try:
        samples = load_samples(dest=d)
        cwes = sorted({s["CWE_ID"] for s in samples})
        print(f"[seccodeplt] {len(samples)} samples loaded, {len(cwes)} distinct CWEs")
    except FileNotFoundError as e:
        print(e)
