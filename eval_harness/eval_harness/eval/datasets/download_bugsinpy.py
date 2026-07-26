"""Download / wrap BugsInPy (Widyasari et al., ESEC/FSE 2020) — the
PRIMARY Bug Detection Agent benchmark (Python-native equivalent of
Defects4J).

Repo verified: https://github.com/soarsmu/BugsInPy — plain git clone, no
manual step needed (unlike PrimeVul/SEC-bench). Structure verified:
  projects/<name>/bugs/<id>/bug.info       (buggy_commit_id, fixed_commit_id, test_file, python_version)
  projects/<name>/bugs/<id>/bug_patch.txt  (the actual fix diff)
  projects/<name>/bugs/<id>/run_test.sh
  framework/bin/bugsinpy-{checkout,test,compile,coverage,info,fuzz,mutation}

17 real Python projects (matplotlib, httpie, PySnooper, fastapi, tqdm,
thefuck, youtube-dl, cookiecutter, sanic, ansible, pandas, spacy, black,
luigi, keras, tornado, scrapy), 493 bugs total.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from eval.common import REPO_ROOT, load_config

REPO_URL = "https://github.com/soarsmu/BugsInPy.git"


def download(dest: Path | None = None) -> Path:
    cfg = load_config()
    dest = dest or REPO_ROOT / cfg["paths"]["dataset_dir"] / "bugsinpy"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not dest.exists():
        subprocess.run(["git", "clone", REPO_URL, str(dest)], check=True)
        print(
            f"[bugsinpy] cloned to {dest}. Add to PATH before running:\n"
            f"  export PATH=$PATH:{dest}/framework/bin\n"
            "Reproducing bugs requires Docker (see the repo's README) — "
            "listing/metadata below works without it."
        )
    else:
        print(f"[bugsinpy] already present at {dest}")
    return dest


def bin_path(name: str, dest: Path | None = None) -> str:
    cfg = load_config()
    dest = dest or REPO_ROOT / cfg["paths"]["dataset_dir"] / "bugsinpy"
    return str(dest / "framework" / "bin" / f"bugsinpy-{name}")


def list_projects(dest: Path | None = None) -> list[str]:
    cfg = load_config()
    dest = dest or REPO_ROOT / cfg["paths"]["dataset_dir"] / "bugsinpy"
    projects_dir = dest / "projects"
    if not projects_dir.exists():
        raise FileNotFoundError(f"{projects_dir} not found — run download() first.")
    return sorted(p.name for p in projects_dir.iterdir() if p.is_dir())


def list_bugs(project: str, dest: Path | None = None) -> list[dict]:
    """Returns bug metadata dicts parsed from each bug.info file — no
    Docker/checkout needed for this, just reads the repo's static metadata.
    """
    cfg = load_config()
    dest = dest or REPO_ROOT / cfg["paths"]["dataset_dir"] / "bugsinpy"
    bugs_dir = dest / "projects" / project / "bugs"
    if not bugs_dir.exists():
        raise FileNotFoundError(f"{bugs_dir} not found for project '{project}'.")

    bugs = []
    for bug_dir in sorted(bugs_dir.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0):
        info_file = bug_dir / "bug.info"
        if not info_file.exists():
            continue
        info: dict[str, str] = {"project": project, "bug_id": bug_dir.name}
        for line in info_file.read_text().splitlines():
            if "=" in line:
                key, _, val = line.partition("=")
                info[key.strip()] = val.strip().strip('"')
        patch_file = bug_dir / "bug_patch.txt"
        info["patch"] = patch_file.read_text() if patch_file.exists() else ""
        bugs.append(info)
    return bugs


def load_sample(sample_n: int | None = None, dest: Path | None = None, case_ids: list[str] | None = None) -> list[dict]:
    """Flat list of bug metadata across all 17 projects, for run_bug_eval.py
    and run_patch_eval.py to consume directly.

    If `case_ids` is given (as "project/bug_id" strings), returns exactly
    those bugs, in the order given — ignoring sample_n. Used by
    eval.shared_cases to guarantee Layer A and Layer B/C score the
    identical underlying examples. Raises if any requested id isn't found.
    """
    cfg = load_config()

    all_bugs = []
    for project in list_projects(dest):
        all_bugs.extend(list_bugs(project, dest))

    if case_ids is not None:
        by_id = {f"{b['project']}/{b['bug_id']}": b for b in all_bugs}
        missing = [i for i in case_ids if i not in by_id]
        if missing:
            raise ValueError(f"BugsInPy case_ids not found: {missing}")
        return [by_id[i] for i in case_ids]

    n = sample_n if sample_n is not None else cfg["sample_sizes"].get("bugsinpy_n")
    if n is not None and n < len(all_bugs):
        all_bugs = all_bugs[:n]
    return all_bugs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=str, default=None)
    args = parser.parse_args()
    d = download(Path(args.dest) if args.dest else None)
    try:
        projects = list_projects(d)
        print(f"[bugsinpy] {len(projects)} projects available: {', '.join(projects)}")
    except FileNotFoundError:
        pass
