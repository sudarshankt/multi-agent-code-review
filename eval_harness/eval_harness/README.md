# Evaluation Harness — Team 10

Standalone, Python-only evaluation code for the Multi-Agent Code Review & Auto-Debugging
System. Scores each agent against a real, git-clonable, Python-native benchmark, with
bootstrap confidence intervals and a zero-shot ablation baseline throughout.

**Scope:** this harness is for **independent, benchmark-based evaluation only**. Layer
B/C's "PR" cases are synthesized from benchmark ground truth (SecCodePLT/BugsInPy), not
pulled from a real repository or an actual submitted PR — that's deliberate, not a gap.
Evaluating one specific real PR against its real fix is a **separate, independent
project** (`eval_PR`, Phase 2) — its own code, its own docs, not part of this repo.

## GUI (recommended starting point)

```bash
pip install -r requirements.txt --break-system-packages
streamlit run gui/app.py
```

A guided interface that explains what each layer measures, lets you pick sample sizes
and which layer(s) to run (A / B / C / all), runs the real harness code underneath (not
a mock), and renders + explains the results with the release-gate verdict. Good for a
first pass or a demo; the CLI commands below give the same results with more control
(exact sample counts, individual benchmarks, scripting into CI).

## Setup

```bash
pip install -r requirements.txt --break-system-packages
```

Each benchmark ships its core data directly in its git repo — a plain clone is enough,
no manual downloads or HuggingFace account needed:

```bash
python -m eval.datasets.download_seccodeplt     # Security
python -m eval.datasets.download_bugsinpy       # Bug Detection
python -m eval.datasets.download_patcheval      # Patch Generation (filters to Python)
python -m eval.datasets.prepare_owasp_cwe
```

## Wiring in the real agents and the judge

Two different things need wiring, and one of them is already done:

- **Per-agent stubs** (`predict_vulnerability`, `predict_bug`, `generate_patch`,
  `style_flags`, `rag_answer_with_context`, `run_full_pipeline` in `eval/agent_interface.py`)
  still return fake/placeholder predictions — these need your actual LangGraph nodes,
  which only your product code can provide. Replace each function body with a call into
  the real agents (see the TODO in each docstring).
- **The judge and zero-shot baseline are already wired to a real API**, not stubs — set
  `ANTHROPIC_API_KEY` and they'll make genuine calls immediately:
  ```bash
  export ANTHROPIC_API_KEY=your-key-here
  ```
  Models are configured via `eval/llm_config.py` (env-var driven — `EVAL_HARNESS_JUDGE_MODEL`,
  `EVAL_HARNESS_BASELINE_MODEL`, `EVAL_HARNESS_MAX_TOKENS`), mirroring the pattern used in
  the separate `eval_PR` project. Without a key, both fall back to a clearly-logged
  placeholder rather than crashing — verified by actually attempting a call with an
  invalid key and confirming a real 401 is caught and handled gracefully.

## Running evals

```bash
python -m eval.runners.run_security_eval
python -m eval.runners.run_bug_eval
python -m eval.runners.run_patch_eval --benchmark patcheval
python -m eval.runners.run_patch_eval --benchmark bugsinpy
python -m eval.runners.run_style_eval --files "src/**/*.py"
python -m eval.runners.run_rag_eval
python -m eval.report.aggregate_results             # merges results/*.json -> final_report.{json,md}
```

Every runner accepts `--n` to override the sample size in `eval/config.yaml` for fast
dev-loop runs; omit it (or set the corresponding `*_n: null` in config) to run full-size
for the final Evaluation Report.

## Human review

Patch correctness and RAG citation grounding need a human pass on top of the automated
score:

```bash
python -m eval.human_eval.sample_for_review --kind patches --n 40
python -m eval.human_eval.sample_for_review --kind citations --n 40
```

This writes a CSV to `eval/human_eval/*_review_sample.csv` for manual pass/fail scoring.

## End-to-end PR review quality (`eval/e2e/`)

Everything above scores individual agents in isolation. `eval/e2e/` scores the FULL
aggregated report your pipeline produces for a whole PR — coverage, noise,
actionability, coherence — using real PR-shaped cases built from BugsInPy/SecCodePLT
ground truth, judged by a strong LLM plus a human-rubric sample for calibration.

```bash
python -m eval.e2e.build_pr_cases          # builds eval/data/e2e_cases.jsonl
python -m eval.e2e.run_e2e_review          # runs the full pipeline + LLM judge
# ... fill in eval/e2e/human_rubric_sample.csv by hand, then:
python -m eval.e2e.calibrate_judge         # correlates judge vs. human scores, applies a trust threshold
```

Case set includes both **positive cases** (a real bug/vuln is present — did the system
catch it?) and **clean/negative cases** (the code is already fixed — did the system
correctly avoid inventing a false positive?), built from SecCodePLT's paired
vulnerable/patched samples. The two are scored and reported separately, never blended
into one average, since a system can look good on one while failing the other.

`run_e2e_review.py` also tracks **per-PR latency** (mean/p50/p95/max wall-clock seconds
for the full pipeline call) automatically — no separate instrumentation needed.

`calibrate_judge.py` computes a Pearson correlation between the judge's scores and your
filled-in human rubric, per dimension, and applies a defined threshold: r≥0.6 = trust the
judge at scale, 0.4–0.6 = spot-check it, below 0.4 = don't rely on it yet for that
dimension.

This needs one thing wired before it produces real numbers:
`agent_interface.run_full_pipeline(pr_diff)` — calls your actual LangGraph supervisor +
all agents together, not an individual agent function. The judge itself
(`eval/e2e/llm_judge.py`'s `_call_judge_llm()`) is already wired to a real, independent
model — just set `ANTHROPIC_API_KEY` (see "Wiring in the real agents and the judge" above).

## Known limitations (not fixed — scope boundaries, stated honestly)

- **Test Generation Agent is not evaluated.** By explicit decision, not oversight —
  only Security, Bug Detection, Patch Generation, Style, and RAG are covered.
- **Style Agent has no independent ground truth.** It's scored against Pylint's own
  output (`run_style_eval.py`), so "agreement with Pylint" is a proxy ceiling, not proof
  the style feedback is actually good — no public benchmark for this exists.
- **BugsInPy has no negative/clean cases** the way SecCodePLT does, since it only ships
  a diff, not full pre/post file text — a real fix would need reconstructing the fixed
  file from the diff (via `git show` against the actual repo) or checking out both
  commits via Docker, neither implemented here.
- **PR diversity is narrow.** Every case (positive and clean) is a single, isolated,
  known bug/vuln in one file. Ordinary real-world PRs — multi-file changes, refactors,
  feature additions — aren't represented, so generalization beyond "one planted issue
  per PR" is unverified.
- **Latency tracking measures the pipeline call only**, not cost (token/dollar spend).
  `LLMCache` records an approximate token-count proxy per cached call
  (`approx_prompt_tokens` / `approx_response_tokens`, char-count/4), but nothing
  aggregates that into a per-PR dollar estimate yet.

See `Overall_Evaluation_Approach_and_Metrics_Summary.md` §6 for the full discussion of
what these limitations mean for how confidently the results can be presented.

## Cross-layer comparison (`eval/shared_cases.py`)

By default, Layer A and Layer B/C sample independently — same benchmark pools, but not
guaranteed to be the same individual examples. `eval/shared_cases.py` fixes a small,
seeded subset of SecCodePLT/BugsInPy examples that every layer can score identically,
enabling a real per-case question: *did the agent get this right alone, but the full
pipeline still miss it?*

```bash
python -m eval.shared_cases --n-seccodeplt 20 --n-bugsinpy 20   # build once, then commit the registry file
python -m eval.runners.run_security_eval --shared
python -m eval.runners.run_bug_eval --shared
python -m eval.e2e.build_pr_cases --shared
python -m eval.e2e.run_e2e_review
python -m eval.report.cross_layer_comparison
```

Build the registry **once** and commit the resulting `eval/data/shared_case_registry.json`
— rebuilding with a different seed or `n` invalidates any comparisons already made
against the old registry. `cross_layer_comparison.py` reports four buckets (both right,
both wrong, agent-right-pipeline-wrong, agent-wrong-pipeline-right) and specifically
calls out the "agent right alone, pipeline wrong" cases — those are worth investigating,
since they suggest another agent or the supervisor is suppressing a correct finding.

## Adversarial (prompt-injection) resistance (`eval/e2e/`)

The system feeds untrusted PR diff content into LLM agents — nothing above tests
whether a crafted PR (e.g., a comment instructing the agent to ignore a real issue) can
manipulate it. This closes that gap.

```bash
python -m eval.e2e.build_adversarial_cases    # 4 hand-crafted attack categories, built from real SecCodePLT vulns
python -m eval.e2e.run_adversarial_eval        # runs the full pipeline + judge, reports a resistance_rate
```

Four attack categories, each pairing a real known vulnerability with an injected
instruction planted nearby (fake "already audited" notes, fake system messages, fake
pre-computed clean scan results, explicit suppression instructions). The correct
behavior is always to flag the real issue regardless of the injection. Any manipulated
case is treated as a security bug, not something to average against good scores — see
the release gate below.

## Release gate — go/no-go (`eval/report/release_gate.py`)

Per-metric targets don't say what *combination* of scores means "ready to ship."
`release_gate.py` applies a rule set declared in `eval/config.yaml`'s `release_gate`
block — **before** results exist, so the bar can't be unconsciously fit to whatever the
first real run produces.

```bash
python -m eval.report.release_gate
```

Checks, in order: every required Layer A metric meets its target; Layer B's positive-case
and clean-case (false-positive) scores clear their floors, and the judge is calibrated
(`TRUST` on every dimension) before being relied on; adversarial resistance rate is
**100%** (any manipulated case blocks release outright, not an average). Prints a
PASS/FAIL/SKIPPED table and an overall verdict, and writes `results/release_gate.json`.

**Layer A checks are CI-aware, not point-estimate-only.** For metrics with a computed
95% bootstrap CI (`SecCodePLT.f1`, `BugsInPy.recall`), the gate checks the CI's *lower
bound* against the target — a lucky sample can't pass a metric that's genuinely
borderline. Metrics without a CI yet (`Pylint-agreement`, `PatchEval-python`) fall back
to the point estimate, and the gate output says so explicitly rather than presenting
every metric as equally rigorous. Tested: a run with point estimates that pass the raw
threshold but whose CI lower bound doesn't correctly now FAILS — this is a real
behavior change from the point-estimate-only version, not just a display difference.

**Regression detection against a committed baseline:**
```bash
python -m eval.report.release_gate --save-baseline   # after a trusted run, e.g. a release
```
Saves the current `final_report.json` to `eval/baseline/final_report.json` — commit this
file. Future gate runs then check whether each CI-backed metric's new interval overlaps
the baseline's; a non-overlapping drop is flagged as a real regression, not sampling
noise. If no baseline has been saved yet, this check reports `SKIPPED`, not a silent
pass. Tested all three states: no baseline (SKIPPED), an overlapping CI against a saved
baseline (PASS), and a deliberately regressed CI with zero overlap (correctly FAIL, with
the non-overlap explained in the detail message).

## What's implemented vs. stubbed

| Runner | Status |
|---|---|
| `agent_interface.py` — `zero_shot_llm_call` | Genuinely wired to the Anthropic API (tested with no key and an invalid key, both handled gracefully) — the one function here that didn't need your product's agent code, just a plain LLM call |
| `agent_interface.py` — `predict_vulnerability`, `predict_bug`, `generate_patch`, `style_flags`, `rag_answer_with_context`, `run_full_pipeline` | Still placeholder stubs — need your actual LangGraph agents, which only your product code can provide |
| `run_security_eval.py` — SecCodePLT | Wired and tested end-to-end against the live repo (once `agent_interface.predict_vulnerability` is real) |
| `run_bug_eval.py` — BugsInPy | Wired and tested against the live repo; currently a recall-only proxy — see its docstring for the checkout step needed for real precision |
| `run_patch_eval.py` — PatchEval, BugsInPy-patch | Wired and tested against live repos with a placeholder pass/fail criterion — swap in each benchmark's own Docker sandbox/test-harness evaluator for real verification |
| `run_style_eval.py` | Fully wired — runs real Pylint/Radon subprocesses |
| `run_rag_eval.py` | Fully wired (needs `ragas` installed + `agent_interface.rag_answer_with_context` real) |
| `eval/metrics/*` | Fully implemented, dependency-light, no stubs |
| `eval/report/aggregate_results.py` | Fully implemented and tested |
| `eval/e2e/build_pr_cases.py` | Fully wired and tested against live BugsInPy/SecCodePLT data, including the positive/clean split |
| `eval/llm_config.py` | Fully implemented — env-var driven model/API-key config, mirrors eval_PR's config.py pattern |
| `eval/e2e/run_e2e_review.py`, `llm_judge.py` | Plumbing (incl. latency tracking) fully tested end-to-end; judge is genuinely wired to the Anthropic API (tested with no key and an invalid key, both handled gracefully) — only `run_full_pipeline` (in `agent_interface.py`) still needs your real agents for a real score |
| `eval/e2e/calibrate_judge.py` | Fully implemented and tested with synthetic correlated/uncorrelated data — ready to run once you've filled in a human rubric sample |
| `eval/e2e/build_adversarial_cases.py`, `run_adversarial_eval.py` | Fully wired and tested against live SecCodePLT data across all 4 attack categories; needs `run_full_pipeline` + `_call_judge_llm` wired for real resistance scores |
| `eval/report/release_gate.py` | Fully implemented and tested — PASS/FAIL/SKIPPED scenarios, CI-lower-bound gating (confirmed it changes the verdict vs. point-estimate-only in a real case), and baseline regression detection across all three states (no baseline, overlapping CI, genuine non-overlapping regression) |
| `eval/shared_cases.py` | Fully wired and tested against live data — confirmed 100% case_id overlap between Layer A `--shared` results and Layer B's case set |
| `eval/report/cross_layer_comparison.py` | Fully implemented and tested with synthetic judge scores — correctly buckets all 4 agreement/disagreement categories |
| `gui/app.py` | Fully implemented and tested — launches cleanly, runs the real harness (verified against live SecCodePLT/BugsInPy/PatchEval data + Style Agent), correctly renders results and the release gate. Found and fixed a real bug in the process: `release_gate.py` couldn't match `--shared` result filenames until its lookup was changed from exact match to prefix match |

See `Evaluation_Harness_Spec.md` (repo root, one level up) for the full spec, benchmark
details, and citations.
