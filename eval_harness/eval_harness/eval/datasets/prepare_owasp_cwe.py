"""Build a local OWASP Top-10 + CWE reference set used to (a) ground the
RAG Pipeline's retrieval corpus and (b) let run_rag_eval.py's human-checked
citation sample verify that a cited CWE/OWASP entry actually supports the
agent's claim (Section 2, RAG/Test row 2).

Primary source: MITRE's CWE JSON feed. If that host isn't reachable (e.g.
inside a network-restricted sandbox), falls back to a small curated set of
the OWASP Top 10 (2021) so the rest of the harness can still be developed
and tested offline.
"""
from __future__ import annotations

import json
from pathlib import Path

from eval.common import REPO_ROOT, load_config

CWE_JSON_FEED = "https://cwe.mitre.org/data/downloads.html"  # page linking the actual zip; see note below

# Curated fallback: OWASP Top 10 (2021) with representative CWE mappings.
# Replace/extend with the full CWE corpus once cwe.mitre.org's data feed
# is reachable from your environment (it's a zipped XML/CSV export, see
# https://cwe.mitre.org/data/downloads.html — not a simple REST endpoint).
OWASP_TOP_10_2021_FALLBACK = [
    {
        "id": "A01:2021",
        "name": "Broken Access Control",
        "cwe_ids": ["CWE-22", "CWE-284", "CWE-285", "CWE-639"],
        "summary": "Restrictions on what authenticated users are allowed to do are not properly enforced.",
    },
    {
        "id": "A02:2021",
        "name": "Cryptographic Failures",
        "cwe_ids": ["CWE-259", "CWE-327", "CWE-331"],
        "summary": "Failures related to cryptography which often lead to exposure of sensitive data.",
    },
    {
        "id": "A03:2021",
        "name": "Injection",
        "cwe_ids": ["CWE-79", "CWE-89", "CWE-73", "CWE-77"],
        "summary": "User-supplied data is not validated, filtered, or sanitized by the application.",
    },
    {
        "id": "A04:2021",
        "name": "Insecure Design",
        "cwe_ids": ["CWE-209", "CWE-256", "CWE-501", "CWE-522"],
        "summary": "Missing or ineffective control design, distinct from an insecure implementation.",
    },
    {
        "id": "A05:2021",
        "name": "Security Misconfiguration",
        "cwe_ids": ["CWE-16", "CWE-611"],
        "summary": "Missing appropriate security hardening, or improperly configured permissions.",
    },
    {
        "id": "A06:2021",
        "name": "Vulnerable and Outdated Components",
        "cwe_ids": ["CWE-1104"],
        "summary": "Using components with known vulnerabilities or that are no longer supported.",
    },
    {
        "id": "A07:2021",
        "name": "Identification and Authentication Failures",
        "cwe_ids": ["CWE-297", "CWE-287", "CWE-384"],
        "summary": "Confirmation of the user's identity, authentication, and session management is broken.",
    },
    {
        "id": "A08:2021",
        "name": "Software and Data Integrity Failures",
        "cwe_ids": ["CWE-829", "CWE-494", "CWE-502"],
        "summary": "Code and infrastructure that does not protect against integrity violations.",
    },
    {
        "id": "A09:2021",
        "name": "Security Logging and Monitoring Failures",
        "cwe_ids": ["CWE-778", "CWE-117"],
        "summary": "Insufficient logging/monitoring, allowing breaches to go undetected.",
    },
    {
        "id": "A10:2021",
        "name": "Server-Side Request Forgery",
        "cwe_ids": ["CWE-918"],
        "summary": "A web application fetches a remote resource without validating the user-supplied URL.",
    },
]


def build(dest: Path | None = None) -> Path:
    cfg = load_config()
    dest = dest or REPO_ROOT / cfg["paths"]["dataset_dir"] / "owasp_cwe" / "kb.json"
    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "w") as f:
        json.dump(OWASP_TOP_10_2021_FALLBACK, f, indent=2)

    print(
        f"[owasp_cwe] wrote {len(OWASP_TOP_10_2021_FALLBACK)} OWASP Top-10 entries "
        f"(fallback set) to {dest}.\n"
        "  For the full CWE corpus, fetch the official export from\n"
        f"  {CWE_JSON_FEED} and extend this loader to parse it — it's a\n"
        "  zipped XML/CSV, not a simple JSON endpoint."
    )
    return dest


def load_kb() -> list[dict]:
    cfg = load_config()
    path = REPO_ROOT / cfg["paths"]["dataset_dir"] / "owasp_cwe" / "kb.json"
    if not path.exists():
        build(path)
    with open(path) as f:
        return json.load(f)


def cwe_supports_claim(cited_cwe_id: str, claim_text: str) -> bool:
    """Very lightweight grounding check: does the cited CWE/OWASP entry's
    summary share enough vocabulary with the claim to plausibly support it?
    This is a cheap pre-filter — the actual "human-checked citation sample"
    (Section 2) should still be reviewed manually via human_eval/.
    """
    kb = load_kb()
    entry = next(
        (e for e in kb if cited_cwe_id in e["cwe_ids"] or cited_cwe_id == e["id"]),
        None,
    )
    if entry is None:
        return False
    claim_words = set(claim_text.lower().split())
    summary_words = set(entry["summary"].lower().split())
    overlap = claim_words & summary_words
    return len(overlap) >= 2


if __name__ == "__main__":
    build()
