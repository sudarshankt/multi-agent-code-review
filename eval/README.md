# Evaluation Harness

This directory contains a standalone evaluation harness for benchmarking the multi-agent code review system.

## What is included

- Metric helpers for precision/recall/F1 and bootstrap confidence intervals in [metrics/classification.py](metrics/classification.py)
- Runner scripts for security, bug, patch, style, RAG, ablation, and project-agent evaluation flows in [runners](runners)
- Dataset download and preparation helpers in [datasets](datasets)
- Human review sampling utilities in [human_eval](human_eval)
- Report aggregation into JSON, Markdown, and HTML outputs in [report](report)
- A top-level entry point in [run_evals.py](run_evals.py)

## Quick start

1. Activate the project environment.
2. Run the focused verification tests and the full evaluation suite:

```bash
. .venv/bin/activate
pytest -q tests/unit/test_eval_harness.py
python eval/run_evals.py
```

3. Review the generated outputs in the [results](../results) directory.

## Output files

The harness writes:

- [results/final_report.json](../results/final_report.json)
- [results/final_report.md](../results/final_report.md)
- [results/evaluation_results.html](../results/evaluation_results.html)
- [results/project_agent_eval.json](../results/project_agent_eval.json)

Each runner also writes its own JSON result file under the results directory.

## Benchmark methodology

The harness is organized around the benchmark categories described in the evaluation spec:

- Security evaluation uses PrimeVul-style vulnerability detection signals and records the dataset path used for the run.
- Bug detection evaluation uses a Defects4J-style checkout and measures binary detection quality.
- Patch generation evaluation uses SEC-bench-style metadata and records the patch success signal.
- Style and RAG evaluation use local OWASP/CWE knowledge assets as the grounding corpus for retrieval and style-related checks.
- An ablation runner captures the zero-shot baseline signal for comparison with the multi-agent workflow.
- The project-agent runner evaluates saved review artifacts emitted by the app pipeline and now consumes both the agent outputs and the preserved per-agent input payloads.

## Project review artifact contract

The app now saves review artifacts with two key fields:

- `agent_results`: the findings emitted by each agent
- `agent_inputs`: the per-agent input payloads used to run each analysis path, including the file map and context object with diffs and bypass counts

This makes the evaluation harness more faithful to the real pipeline because it can score the agent inputs as well as the downstream findings.

## Report format

Each runner writes a JSON payload with a benchmark name, agent label, sample size, metric values, and a baseline comparison. The aggregator merges all runner outputs into:

- [results/final_report.json](../results/final_report.json)
- [results/final_report.md](../results/final_report.md)

The markdown report is intended to be copied into the evaluation report deliverable.

## Notes

- The current implementation uses real benchmark repository checkouts when available (PrimeVul, SEC-bench, Defects4J) and local OWASP/CWE knowledge files for retrieval-oriented evaluation.
- For app-generated review artifacts, the harness is designed to consume the same data that the product uses at runtime.
