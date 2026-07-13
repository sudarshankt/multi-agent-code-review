# Eval Usage Guide

## Running the harness

From the repository root:

```bash
. .venv/bin/activate
pytest -q tests/unit/test_eval_harness.py
python eval/run_evals.py
```

This executes all runner modules and writes report artifacts to the results directory.

## Adding a new runner

1. Create a new script in [runners](runners)
2. Implement a function that returns a JSON-serializable result payload
3. Import and invoke it from [run_evals.py](run_evals.py)
4. Add tests for the new logic under [tests/unit](../tests/unit)

## Dataset expectations

The download helpers in [datasets](datasets) try to populate benchmark repositories locally. If a repository cannot be cloned, the harness falls back to placeholder metadata files so the run still completes.

## Interpreting the results

- Open [results/final_report.md](../results/final_report.md) for a compact table suitable for the evaluation report.
- Use [results/final_report.json](../results/final_report.json) when you need machine-readable metrics for later aggregation or plotting.
- Open [results/evaluation_results.html](../results/evaluation_results.html) for a simple browser-based view of the aggregate scores.
- Compare each runner's metric against the included `baseline_zero_shot` value to understand the uplift from the multi-agent or retrieval workflow.

## How to use this eval with project agent outputs

The harness is meant to score the outputs produced by the project agents, not to replace the app pipeline.

1. Capture agent inputs and outputs from a real review run.
   - Inputs are the PR file map, diffs, and any retrieved context supplied to the agent.
   - Outputs are the findings or patches emitted by the agent.

2. Persist those values in the review artifact.
   - The current app pipeline records them under `review.agent_inputs` and `review.agent_results`.
   - This is the contract the eval runner uses for the project-agent path.

3. Map those outputs into the evaluation schema.
   - Security and bug agents should produce binary labels such as vulnerable/buggy vs. not-vulnerable/not-buggy.
   - Patch-generation outputs should be treated as patch candidates with a pass/fail outcome.
   - Style and RAG outputs should be converted into the metric fields already used by the runners, such as agreement or faithfulness.

4. Feed the mapped results into a new runner.
   - Create a runner under [runners](runners) that loads the saved review object.
   - Convert each sample into the expected metric input and return a payload shaped like the existing runners.

5. Run the harness again.
   - The main entry point [run_evals.py](run_evals.py) will aggregate the new runner results into the shared report files.

A practical pattern is:

```python
from src.models.review import Review

review = Review.model_validate_json(open("path/to/review.json").read())
# Use review.agent_inputs and review.agent_results as the evaluation source
```

This keeps the eval harness separate from the live app logic while letting you benchmark the same agent inputs and outputs that the product uses.
