# Evaluation Harness — Build Instructions
**Team 10 — Multi-Agent Code Review & Auto-Debugging System**
*Use this document later as the spec when generating the actual evaluation code.*

---

## 1. Purpose

Build a standalone evaluation harness (separate from the app pipeline) that scores each
agent against a named benchmark, logs results, and produces the metrics needed for the
Evaluation Report deliverable (Phase 4). One script per agent, one shared results schema,
one aggregator that rolls everything into a final report.

## 2. Benchmarks to wire up, per agent

Every agent below lists **(a)** the benchmark(s) already named in the June 28 proposal /
Slide 16, kept for continuity, and **(b)** the benchmark(s) added after our comparative-
benchmark analysis (see the deck's "Comparative Benchmarks by Agent" and "Why We Added
New Benchmarks" slides). Build runners for **both** — the proposal benchmarks stay in
the report for traceability, the added ones are what the headline numbers should actually
be judged against.

### Security Agent

| # | Benchmark | Status | Get the data | What to compute |
|---|---|---|---|---|
| 1 | CodeXGLUE Defect Detection | *from proposal* | https://github.com/microsoft/CodeXGLUE | Precision/Recall/F1; report **alongside** PrimeVul with a note that CodeXGLUE-style splits are known to be optimistic (PrimeVul's finding: 68% F1 on BigVul → ~3% on PrimeVul) |
| 2 | SonarQube / Checkmarx OWASP-10 precision (60–80%) | *from proposal* | Vendor-reported; no dataset to run — keep as a citation-only comparator, not a runnable benchmark | N/A (contextual reference only) |
| 3 | **PrimeVul** | *added* | https://github.com/DLVulDet/PrimeVul (Ding et al., ICSE 2025) | Precision, Recall, F1 on the **temporal, deduplicated split** |
| 4 | **CyberSecEval** (Meta) | *added* | https://github.com/meta-llama/PurpleLlama/tree/main/CybersecurityBenchmarks | Insecure-code-generation rate / security-assistance score, as a secondary check on the Security Agent's own output |

### Bug Detection Agent

| # | Benchmark | Status | Get the data | What to compute |
|---|---|---|---|---|
| 1 | Defects4J fault localization (40–60%) | *from proposal* | https://github.com/rjust/defects4j | Fault localization accuracy on the standard Defects4J split (Java — see §5 note) |
| 2 | **Repo-level detection (JITVul-style)** | *added* | Follow methodology in Yildiz et al., ACL 2025 (arXiv/ACL 2025.acl-long.1490) — build a small internal repo-level test set if the original isn't public | Detection accuracy when bugs are found in full-repo context rather than isolated functions, matching how the AST+LLM agent actually operates |

### Style & Performance Agent

| # | Benchmark | Status | Get the data | What to compute |
|---|---|---|---|---|
| 1 | Pylint agreement (>90% target) | *from proposal* | Run Pylint directly on the same file set | % agreement between agent flags and Pylint's own flags; false-positive rate = agent flags not in Pylint |
| 2 | **Radon complexity ground-truth spot-check** | *added* | Run Radon directly (cyclomatic/cognitive/Halstead) on a sampled subset | Compare agent-reported complexity scores against Radon's own computed values, not just presence/absence of a flag |

### Patch Generation Agent

| # | Benchmark | Status | Get the data | What to compute |
|---|---|---|---|---|
| 1 | Defects4J patch pass rate (target >70%) | *from proposal* | https://github.com/rjust/defects4j | Fraction of generated patches whose associated tests pass |
| 2 | **SEC-bench** | *added* | https://github.com/Sec-bench/Sec-bench (Lee et al., 2025, arXiv:2506.11791) | PoC reproduction rate, patch success rate on real, exploited CVEs — compare against the reported SOTA ceiling (~18% / ~34%) |
| 3 | **PatchEval** | *added* | Wei et al., 2025, arXiv:2511.11019 | Patch correctness on real-world vulnerability patching tasks — a second, independent check alongside SEC-bench |
| 4 | Human-reviewed patch sample | *added* | Internal — sample 30–50 generated patches | Human-rated pass/fail + short rationale, to sanity-check the automated Patch Pass Rate (catches patches that pass tests but are wrong/unsafe) |

### RAG Pipeline / Test Generation

| # | Benchmark | Status | Get the data | What to compute |
|---|---|---|---|---|
| 1 | RAGAS Faithfulness >0.75, Answer Relevance >0.70 | *from proposal* | `pip install ragas` — https://github.com/explodinggecko/ragas | Faithfulness, Answer Relevance, Context Precision/Recall over OWASP/CWE retrieval traces |
| 2 | **Human-checked OWASP/CWE citation sample** | *added* | Internal — sample retrieved citations | Manual accuracy check: does the cited OWASP/CWE entry actually support the agent's claim? Domain-grounds the generic RAGAS thresholds |

### Cross-cutting (all agents)

| # | Benchmark | Status | Get the data | What to compute |
|---|---|---|---|---|
| 1 | **Zero-shot single-LLM ablation baseline** | *added* | N/A — internal | Run the same test set through one zero-shot LLM call (no LangGraph, no RAG, no supervisor) to quantify the delta the multi-agent + RAG architecture adds over each metric above |

## 3. Repo layout to generate

```
eval/
  __init__.py
  datasets/
    download_primevul.py
    download_secbench.py
    download_defects4j.py
    prepare_owasp_cwe.py
  runners/
    run_security_eval.py       # PrimeVul + CodeXGLUE + CyberSecEval
    run_bug_eval.py             # Defects4J fault localization + repo-level (JITVul-style)
    run_patch_eval.py           # Defects4J pass rate + SEC-bench + PatchEval
    run_style_eval.py           # Pylint agreement + Radon ground-truth spot-check
    run_rag_eval.py             # RAGAS + human-checked citation sample
    run_ablation_eval.py        # zero-shot single-LLM baseline, run against every benchmark above
  metrics/
    classification.py           # precision/recall/F1, confusion matrix
    ragas_wrapper.py
    stats.py                    # bootstrap CI, since LLM output is non-deterministic
  human_eval/
    sample_for_review.py        # pulls N patches for manual scoring
    review_template.csv
  report/
    aggregate_results.py        # merges all runner outputs into final_report.json + .md
  config.yaml                   # dataset paths, sample sizes, thresholds
results/                        # gitignored, runner outputs land here
```

## 4. Metrics — exact definitions to implement

- **Precision / Recall / F1**: standard binary classification on vulnerable vs. not-vulnerable (or buggy vs. not) at the function level.
- **Confidence intervals**: bootstrap resample (n=1000) over the test set for every headline metric — LLM outputs are non-deterministic, so a single-run point estimate is not enough. Report as `metric ± CI`.
- **Patch Pass Rate**: fraction of generated patches for which the associated test suite passes AND the patch does not just delete/weaken the failing test (add a check that diffs the test file — flag if the patch touched test files).
- **PEP8 Agreement**: (agent flags ∩ Pylint flags) / (Pylint flags), plus false-positive rate (agent flags ∉ Pylint flags).
- **RAGAS Faithfulness / Answer Relevance**: use the `ragas` library's built-in metrics against retrieved OWASP/CWE chunks + generated citation text.
- **Ablation baseline**: for every headline metric, also run the **single zero-shot LLM call** (no LangGraph, no RAG, no supervisor) on the same test set, so the report can show the delta the multi-agent + RAG architecture actually adds. This directly answers the "why 5 agents instead of one prompt" evaluation gap.

## 5. Known constraints to flag in the code (don't silently skip)

- Defects4J is Java-only; the rest of the pipeline is scoped to Python in the proposal. Either (a) restrict Defects4J to the Bug/Patch agents' cross-language reasoning claim only, or (b) swap in a Python-native bug benchmark (e.g., BugsInPy) and say so explicitly in the report. Pick one before writing `run_bug_eval.py`.
- PrimeVul and SEC-bench are large/slow to run in full — build `config.yaml` sample-size knobs (`primevul_n`, `secbench_n`) so eval can run on a subset during development and full-size only for the final report.
- Cache every LLM call to disk (`eval/cache/`) keyed by prompt hash — reruns during development should not re-spend API budget.

## 6. Output format (for `aggregate_results.py`)

Each runner writes a JSON like:
```json
{
  "benchmark": "PrimeVul",
  "agent": "security",
  "n": 500,
  "metrics": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "f1_ci95": [0.0, 0.0]},
  "baseline_zero_shot": {"f1": 0.0},
  "timestamp": "ISO8601"
}
```
The aggregator merges all runner JSONs into one `final_report.json` and renders a markdown
table for the Evaluation Report deliverable.

## 7. References (for citing in code comments / report)

**From the original proposal (Section 6 / Slide 16):**
- Lu, S. et al. (2021). *CodeXGLUE.* https://github.com/microsoft/CodeXGLUE
- Just, R. et al. (2014). *Defects4J: A Database of Existing Faults.* https://github.com/rjust/defects4j
- Feng, Z. et al. (2020). *CodeBERT.* arXiv:2002.08155
- SonarQube / Checkmarx OWASP Top-10 precision figures — vendor-reported, cited for context only (no runnable dataset)

**Added after our comparative-benchmark analysis:**
- Ding, Y. et al. (2025). *PrimeVul: Realistic Vulnerability Detection Benchmark.* ICSE 2025.
- Lee, H. et al. (2025). *SEC-bench: Automated Benchmarking of LLM Agents on Real-World Software Security Tasks.* arXiv:2506.11791.
- Wei, Z. et al. (2025). *PatchEval: A New Benchmark for Evaluating LLMs on Patching Real-World Vulnerabilities.* arXiv:2511.11019.
- Yildiz, A. et al. (2025). *Benchmarking LLMs and LLM-based Agents in Practical Vulnerability Detection for Code Repositories.* ACL 2025 (2025.acl-long.1490) — JITVul repo-level methodology.
- Meta. *CyberSecEval.* https://github.com/meta-llama/PurpleLlama/tree/main/CybersecurityBenchmarks
- Es, S. et al. (2023). *RAGAS: Automated Evaluation of RAG.* arXiv:2309.15217
- Radon (complexity metrics library) — used directly, no external paper: https://radon.readthedocs.io

---
*Next step: hand this file to Claude (or the dev assigned to Eval) with "generate the code for eval/ per this spec" to produce the actual runners.*
