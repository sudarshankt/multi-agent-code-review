# ASVS Integration Proposal — Security Agent

**Status:** Draft — for review, not yet implemented
**Source standard:** OWASP Application Security Verification Standard (ASVS), v5.0.0
**Source repo:** https://github.com/OWASP/ASVS
**Related docs:** `001-security-agent-current.md`, `001-security-agent-enhanced.md`

---

## 1. Objective

Add ASVS as a second knowledge source alongside the existing OWASP/CWE knowledge base, so Security Agent findings can cite specific, checkable ASVS requirement IDs (e.g. `v5.0.0-6.1.2`) in addition to CWE categories. This is additive — it does not replace the current CWE-based retrieval, it sits next to it.

## 2. Why ASVS, briefly

CWE/OWASP Top 10 tells you *what kind of bug* to look for (a taxonomy). ASVS tells you *whether a specific, numbered control exists and is implemented correctly* (a checklist), organized by chapter/section, with each requirement tagged to verification level L1/L2/L3 (baseline → sensitive-data apps → high-assurance systems). Findings grounded in specific requirement text are more consistent and more auditable than open-ended "find vulnerabilities" prompting.

## 3. Data source & licensing

- **Primary source:** `OWASP/ASVS` GitHub repo, `v5.0.0` release tag (current stable; released May 2025). Official machine-readable exports (CSV, JSON, XML) are published on the GitHub Releases page alongside the PDF/DOCX — this is the same standard, not a third-party derivative.
- **Format:** the JSON export is a flat list of requirement objects, each with `id`, `text` (the requirement description), and `file` (source chapter file) — plus chapter/section/level metadata from the CSV export (`chapter_id`, `chapter_name`, `section_id`, `section_name`, `req_id`, `req_description`, `level1/2/3`, `cwe`, `nist`).
- **Versioning discipline:** ASVS explicitly recommends citing requirements as `v<version>-<chapter>.<section>.<requirement>` (e.g. `v5.0.0-1.2.5`) precisely because requirement numbering has changed between major versions (4.0.3 → 5.0.0 renumbered extensively). **We must pin and store the ASVS version alongside every ingested requirement and every finding**, or citations silently rot when ASVS releases a new version.
- **Licensing:** OWASP publishes ASVS as an open, free-to-use standard — confirm the exact license text (historically Creative Commons Attribution-ShareAlike) and add an attribution note in our docs before shipping, since we are not a third party seeking to bypass this — it's a two-minute check I have not personally verified against the current repo's `LICENSE` file.

## 4. Where this integrates (mapped to your existing architecture)

Mirrors the existing `SecurityRetriever` / ChromaDB / `security.j2` pattern described in `001-security-agent-current.md` — same shape, new collection.

## 5. Files to add or update (proposed — not yet created)

| File | Change | New or existing |
|---|---|---|
| `scripts/ingest_asvs.py` | Downloads/parses official ASVS JSON+CSV export, chunks per-requirement, embeds into a new ChromaDB collection `asvs_knowledge` with metadata (`asvs_id`, `version`, `level`, `chapter`, `section`, `cwe`) | New — parallels existing `scripts/ingest_owasp.py` |
| `src/agents/security/asvs_retriever.py` | `ASVSRetriever` class — queries `asvs_knowledge`, optionally filtered by target level (L1/L2/L3) and/or CWE match from triage | New — parallels `retriever.py`'s `SecurityRetriever` |
| `src/prompts/templates/security.j2` | Add an ASVS context block (same pattern as existing CWE injection) + instruct the LLM to include matched `asvs_id` in its JSON output | Update existing |
| `src/agents/parsing.py` | Extend `findings_from_llm()` to extract/validate an `asvs_id` (or list of IDs) field, defaulting to empty if absent | Update existing |
| Finding schema (`SecurityFinding` in the enhanced doc's proposed `schemas.py`, or the current dataclass if not yet on Pydantic v2) | Add `asvs_id: list[str]` and `asvs_level: str \| None` fields | Update existing / update proposed schema |
| `src/services/llm_service.py` / `settings` | New config: `ASVS_VERSION` (default `"5.0.0"`), `ASVS_TARGET_LEVEL` (default `"L2"` — matches ASVS's own recommended default for most business apps), `ASVS_DATA_SOURCE` (`local`/`remote`, same fallback pattern as ChromaDB) | Update existing config table |
| `tests/unit/test_asvs_retriever.py` | Unit tests: level filtering, fallback behavior, formatting | New — parallels `test_security_retriever.py` |
| `tests/unit/test_security_parsing.py` | Add cases for `asvs_id` extraction/validation | Update existing |
| **`docs/architecture/agents/001-security-agent-current.md`** | Add ASVS to the Dependencies and Configuration tables once implemented (this doc currently only reflects what's *actually built*) | Update existing — only after implementation, not before |
| **`docs/architecture/agents/004-asvs-integration.md`** | This proposal, once approved, becomes the permanent design record | New — this file |
| **`docs/project-proposal/proposal.md`** | If the project's stated success metrics/scope should mention ASVS coverage as a goal — I haven't read this file yet, so can't say whether it needs updating; worth checking once I have its contents | Possibly update |

## 6. Rollout phasing (so this stays additive and low-risk)

**Phase 1 — Ingestion only.** Build `ingest_asvs.py`, populate `asvs_knowledge`, no behavior change to the agent yet. Verify data quality (spot-check requirement text against the official PDF/CSV).

**Phase 2 — Retrieval, no prompt change.** Add `ASVSRetriever`, wire it into `SecurityAgent.analyze()`, but don't yet change `security.j2` — just confirm retrieval quality/latency in isolation (log what would be retrieved, don't feed it to the LLM yet).

**Phase 3 — Prompt integration.** Update `security.j2` to inject ASVS context and request `asvs_id` citations; update parsing/schema to capture it. This is the first phase that changes actual findings output.

**Phase 4 (optional) — Level-driven rigor.** Let `ASVS_TARGET_LEVEL` per-repo/per-config drive which tier of requirements gets retrieved — ties into the "triage" enhancement already proposed in `001-security-agent-enhanced.md`.

Each phase is independently shippable and testable — you can stop after Phase 2 if you decide prompt changes need more validation first.

## 7. Open questions before implementation

1. Target ASVS level default — L2 (recommended default for most business apps) or should this be configurable per-repo from day one?
2. Should `ASVSRetriever` reuse the existing `SecurityRetriever`'s ChromaDB client/connection, or is a separate collection enough isolation?
3. Do we want CWE↔ASVS cross-referencing (the official CSV includes a `cwe` column per requirement) to let triage (Bandit/CWE hits) directly narrow ASVS retrieval? This would materially help Enhancement 1 and Enhancement 3 from the existing enhanced doc.
4. Update cadence — ASVS ships periodic patch releases (5.0.1 next); do we manually re-run `ingest_asvs.py` on new releases, or automate a check?

---

*This is a proposal for review. No source files or repo content have been modified.*
