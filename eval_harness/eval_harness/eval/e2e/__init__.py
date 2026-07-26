"""End-to-end PR review quality evaluation.

Unlike eval/runners/*.py, which score individual agent functions in
isolation, this package scores the FULL aggregated report your multi-agent
pipeline produces for a whole PR — coverage, noise, actionability, and
coherence — using a curated set of real PRs with known ground truth,
scored by both an LLM judge and a small human-rubric sample.

See eval/e2e/README.md (or the E2E section of Evaluation_Harness_Spec.md)
for the full approach.
"""
