# Evaluation Pipeline

This directory evaluates the PR-review system in three layers:

1. **`finding_eval`** — each finding agent (`security`, `bug_detection`, `style`,
   `performance`) treated as a **classifier**: does it correctly flag the
   issues in a known file, scored with precision/recall/F1.
2. **`fix_eval`** — the fix agent treated as a **generator**: given a clean,
   known-correct finding, does it produce a good patch, scored by an
   **LLM-as-judge** across candidate models.
3. **`e2e_eval`** — the **pipeline**: run finding_eval's live agent output
   straight into fix_eval's judged fix step, so the two stages are no longer
   evaluated in isolation from each other.

All three read the same golden dataset (`eval/golden/manifest.json`) and write
timestamped + `latest.json` reports under `eval/results/<stage>/`. The
dashboard's Eval Matrix page reads `latest.json` from all three via
`GET /api/v1/eval/latest`, `/latest-fix`, `/latest-e2e`.

## The golden dataset

`eval/golden/manifest.json` is keyed by agent name (`security`,
`bug_detection`, `style`, `performance`). Each entry is a file plus the
list of issues a human has confirmed exist in it:

```json
{
  "security": [
    {
      "file": "tests/test_data/app_vunerable.py",
      "expected": [
        {
          "description": "Hardcoded API key / secret in source",
          "start_line": 9,
          "end_line": 9,
          "severity": "critical"
        }
      ]
    }
  ]
}
```

This is the only ground truth in the whole pipeline — everything below is
scored against it.

---

## 1. Finding agents — classification (`finding_eval`)

**Concept:** a finding agent's job is binary per potential issue — did it
notice this problem or not — so it's scored like a classifier, not judged
for prose quality.

**How matching works** (`eval/finding_eval/scoring.py`): for each golden
file, the agent runs for real (`agent.run(files, ...)`), then each expected
finding is greedily paired with an actual finding whose line range overlaps
(±2 lines tolerance), breaking ties by embedding/text similarity between the
descriptions. Severity is *not* required to match — agents may reasonably
disagree on severity tier while still correctly identifying the issue.

- **Matched** → true positive (TP)
- **Expected but no overlapping actual finding** → false negative (FN, "missed")
- **Actual finding with no overlapping expected finding** → false positive (FP, "unexpected")

**Metrics reported per agent:**

| Metric | Meaning |
|---|---|
| `precision` | `TP / (TP + FP)` — of what it flagged, how much was real |
| `recall` | `TP / (TP + FN)` — of what's real, how much it caught |
| `f1` | harmonic mean of precision & recall |
| `avg_similarity` | mean description similarity across matched pairs (quality of the *match*, not a metric on its own) |

**Run it:**

```bash
python -m eval.finding_eval.run_eval                       # all agents
python -m eval.finding_eval.run_eval --agent security,style # subset
```

Results: `eval/results/finding/run-XXXX.json` + `latest.json`.

---

## 2. Fix agent — LLM-as-judge (`fix_eval`)

**Concept:** there's no ground-truth "correct patch" to diff against — fixes
are generated text, so a judge LLM rates the output against a rubric
instead. This eval is deliberately **decoupled from the finding agents**:
findings are synthesized directly from `eval/golden/manifest.json`'s
`expected` entries (see `load_golden_findings()`), not from a live
finding-agent run. That isolation is intentional — it measures fix quality
independent of whether the finding agents are currently any good, so a
finding-agent regression can never masquerade as a fix-agent regression.

**How it works** (`eval/fix_eval/run_eval.py`): for each model candidate in
`eval/fix_eval/model_candidates.json`, `FixAgent._fix_file()` is called
directly per golden case (no git dependency, no severity/file-count gating
from `FixAgent.run()`). The resulting diff is checked for valid Python
syntax, then sent to a judge LLM (`src/prompts/templates/fix_judge.j2`)
along with the original code, fixed code, and the findings it was meant to
address. The judge returns:

| Field | Meaning |
|---|---|
| `resolved` | did the fix actually address the underlying issue |
| `correctness` | 0-1 |
| `safety` | 0-1 — did it introduce new risk |
| `minimality` | 0-1 — scope discipline, no unrelated changes |
| `explanation_quality` | 0-1 |

The judge LLM is prompted to score each rubric dimension directly as a 0-1
float, so every field in this eval — rates and rubric scores alike — lands
on the same 0-1 scale.

Aggregated per model candidate: `success_rate` (LLM returned usable code),
`syntax_valid_rate`, `resolved_rate`, and the mean of each rubric score.

**Run it:**

```bash
python -m eval.fix_eval.run_eval                    # all candidates in model_candidates.json
python -m eval.fix_eval.run_eval --models nav        # subset by label
```

Results: `eval/results/fix/run-XXXX.json` + `latest.json`.

**Add a model candidate:** append to `eval/fix_eval/model_candidates.json`,
e.g. `{"label": "deepseek", "model_provider": "deepseek", "primary_model": "deepseek-chat"}`.

---

## 3. End-to-end pipeline (`e2e_eval`)

**Concept:** stages 1 and 2 are each useful for isolating *which* stage
regressed, but neither can catch a **compounding failure across the
handoff** — e.g. a finding agent that reports a slightly-off line range or a
vague description, which the fix agent then mishandles even though both
components look fine when tested independently (`fix_eval` always hands the
fixer clean, golden-derived findings; it never sees what the finder
actually produces).

**How it works** (`eval/e2e_eval/run_eval.py`): runs each finding agent
live, matches its output against the golden manifest exactly like
`finding_eval` does, then feeds **only the actual matched findings** (not
golden-derived ones) into `FixAgent._fix_file()` and judges the result with
the same `fix_judge.j2` prompt as `fix_eval`.

**Metrics reported per agent** — finding-stage precision/recall/F1 as
before, plus:

| Metric | Meaning |
|---|---|
| `fix_success_rate` | of fix attempts, how many produced valid usable code (mechanical, no LLM judgment) |
| `resolved_rate` | of judged fixes, how many the judge marked `resolved` |

**Run it:**

```bash
python -m eval.e2e_eval.run_eval                       # all agents
python -m eval.e2e_eval.run_eval --agent security       # subset
```

Results: `eval/results/e2e/run-XXXX.json` + `latest.json`.

---

## Which eval do I run for what?

| You changed... | Run this | Why |
|---|---|---|
| A finding agent's prompt/logic | `finding_eval` | Isolates precision/recall without fix-agent noise |
| The fix agent's prompt/logic | `fix_eval` | Isolates fix quality against clean, known-good findings |
| Anything in the finding→fix handoff (schema, location fields, category names) | `e2e_eval` | Only this eval exercises the real handoff |
| Before a release / periodically | All three | `finding_eval` + `fix_eval` first (cheaper, isolate regressions), `e2e_eval` to confirm the pipeline as a whole still resolves issues |

## Metric glossary

Every metric that appears in a `latest.json` report or the dashboard's Eval
Matrix page, in one place. `TP`/`FP`/`FN` below always mean: matched against
`eval/golden/manifest.json` using the ±2-line-tolerance matching described
in [Finding agents](#1-finding-agents--classification-finding_eval) above.

**Finding-stage** (reported by `finding_eval`, and by `e2e_eval` per agent):

| Metric | Formula / definition | Reading it |
|---|---|---|
| `true_positives` | count of expected findings matched to an actual finding | raw count, not a rate |
| `false_positives` | count of actual findings with no matching expected finding | "unexpected" flags — noise |
| `false_negatives` | count of expected findings with no matching actual finding | "missed" issues — the agent's blind spots |
| `precision` | `TP / (TP + FP)` | of what the agent flagged, how much was real. Low precision = noisy/over-flagging |
| `recall` | `TP / (TP + FN)` | of what's actually wrong, how much the agent caught. Low recall = missing real issues |
| `f1` | `2 · precision · recall / (precision + recall)` | single balanced score between precision and recall |
| `avg_similarity` | mean text/embedding similarity between each matched pair's expected vs. actual description | describes match *quality*, not agent quality — a low value here means matches are shaky even where line ranges overlapped |

**Fix-stage** (reported by `fix_eval` per model candidate, and by `e2e_eval`
per agent — dashboard column names differ slightly between the two tables,
noted below):

| Metric | Formula / definition | Reading it |
|---|---|---|
| `success_rate` (`fix_eval`) / `fix_success_rate` (`e2e_eval`) — shown as **"Fix Generated"** in the dashboard | `attempts producing usable code / total attempts` | purely mechanical — did the fix agent return *something* it considered a valid patch, no judgment on whether the patch is any good |
| `syntax_valid_rate` | `attempts that parse as valid Python / attempts checked` | mechanical syntax check on the generated code, independent of the judge |
| `resolved_rate` | `judged fixes where judge.resolved == true / judged fixes` | the judge LLM's own binary verdict — did this patch actually address the finding |
| `avg_correctness` | mean of judge's `correctness` score (0-1) across judged fixes | does the fix work, per the judge's read of the diff |
| `avg_safety` | mean of judge's `safety` score (0-1) across judged fixes | did the fix avoid introducing new bugs or touching unrelated behavior |
| `avg_minimality` | mean of judge's `minimality` score (0-1) across judged fixes | is the diff scoped to the finding, not a drive-by rewrite |
| `avg_explanation_quality` | mean of judge's `explanation_quality` score (0-1) across judged fixes | is the agent's stated explanation of its own change accurate and clear |

All rate metrics (`precision`, `recall`, `f1`, `success_rate`/`fix_success_rate`,
`syntax_valid_rate`, `resolved_rate`) and all rubric averages
(`avg_correctness`, `avg_safety`, `avg_minimality`, `avg_explanation_quality`)
share the same 0-1 scale, so they're directly comparable at a glance —
nothing in this pipeline reports on a 0-5 or percentage scale.

## Viewing results

The dashboard's Eval Matrix page (`dashboard/src/pages/EvalMatrix.tsx`)
renders all three `latest.json` reports automatically — start the app
(see the root `README.md` / `QUICKSTART.md`) and open the Eval Matrix tab.
No need to re-run anything to view already-generated results; the API just
serves whatever is currently in `eval/results/*/latest.json`.
