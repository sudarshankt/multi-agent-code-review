"""Evaluation Harness GUI — Streamlit app.

A guided interface over the eval harness: explains what it measures, lets
you pick how many samples to test and which layer(s) to run, runs the
real harness code (not a mock — this imports and calls the actual runner
functions), and renders + explains the results.

Run with:
    cd eval_harness
    pip install -r requirements.txt streamlit --break-system-packages
    streamlit run gui/app.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval.common import load_config  # noqa: E402
from eval.llm_config import AVAILABLE_MODELS, api_key_configured, get_baseline_model, get_judge_model  # noqa: E402

st.set_page_config(page_title="Multi-Agent Code Review — Evaluation Harness", layout="wide")

CFG = load_config()
RESULTS_DIR = REPO_ROOT / CFG["paths"]["results_dir"]
DATA_DIR = REPO_ROOT / CFG["paths"]["dataset_dir"]

if "run_log" not in st.session_state:
    st.session_state.run_log = []
if "last_run_layers" not in st.session_state:
    st.session_state.last_run_layers = []


# ============================================================================
# Helpers
# ============================================================================

def log(msg: str) -> None:
    st.session_state.run_log.append(msg)


def dataset_status() -> dict:
    from eval.datasets.download_patcheval import DATA_REL_PATHS as PATCHEVAL_DATA_REL_PATHS

    patcheval_dest = DATA_DIR / "patcheval"
    return {
        "SecCodePLT (Security)": (DATA_DIR / "seccodeplt" / "virtue_code_eval" / "data" / "safety" / "secodeplt" / "data.json").exists(),
        "BugsInPy (Bug Detection)": (DATA_DIR / "bugsinpy" / "projects").exists(),
        "PatchEval (Patch Generation)": any((patcheval_dest / p).exists() for p in PATCHEVAL_DATA_REL_PATHS),
    }


@st.cache_data(show_spinner=False)
def dataset_counts() -> dict:
    """Actual sample counts available on disk for each dataset, so the
    sidebar sliders can't be dragged past what's really there. None means
    "not downloaded yet" — callers should fall back to a placeholder max.
    Cached per Streamlit session; the "Download missing datasets" button
    clears this cache so counts refresh right after a download.
    """
    counts: dict[str, int | None] = {"seccodeplt": None, "bugsinpy": None, "patcheval": None}
    try:
        from eval.datasets.download_seccodeplt import load_samples

        counts["seccodeplt"] = len(load_samples(sample_n=10**9))
    except Exception:
        pass
    try:
        from eval.datasets.download_bugsinpy import load_sample

        counts["bugsinpy"] = len(load_sample(sample_n=10**9))
    except Exception:
        pass
    try:
        from eval.datasets.download_patcheval import load_python_subset

        counts["patcheval"] = len(load_python_subset(sample_n=10**9))
    except Exception:
        pass
    return counts


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def metric_card(label: str, value, target=None, higher_is_better: bool = True, help_text: str = "") -> None:
    if value is None:
        st.metric(label, "—", help=help_text)
        return
    delta = None
    if target is not None:
        met = (value >= target) if higher_is_better else (value <= target)
        delta = f"{'✅ meets' if met else '❌ below'} target {target}"
    st.metric(label, f"{value:.3f}" if isinstance(value, float) else value, delta=delta, help=help_text)


# ============================================================================
# Header
# ============================================================================

st.title("🔍 Evaluation Harness — Multi-Agent Code Review System")
st.markdown(
    "This tool answers one question: **is the multi-agent code-review pipeline actually "
    "good, and how do we know?** It scores the agents individually, scores the whole "
    "system on realistic PRs, checks whether it can be tricked, and applies a go/no-go "
    "release verdict — all against real, verified benchmarks, never invented numbers."
)

with st.expander("📖 What does each layer measure? (read this first)", expanded=True):
    st.markdown(
        """
| Layer | Question it answers | What it runs |
|---|---|---|
| **A — Per-agent** | Is each agent individually good at its narrow job? | Security Agent vs. SecCodePLT, Bug Agent vs. BugsInPy, Patch Agent vs. PatchEval, Style Agent vs. Pylint |
| **B — End-to-end** | Does the *whole system* produce a PR review a developer would trust? | Full pipeline on real PR-shaped cases — both real bugs (does it catch them?) and clean code (does it stay quiet?) |
| **C — Safety & release** | Can it be tricked by content inside the code it reviews, and is it ready to ship? | 4 prompt-injection attack tests, then a go/no-go verdict combining A+B+C |

**Every score is compared against a zero-shot baseline** (one plain LLM call, no agents)
— that comparison, not the raw number, is the real evidence the multi-agent design is
worth its complexity.

**Integration status:** `eval/agent_interface.py`'s functions are wired to the real
LangGraph agents (Security, Bug Detection, Style, Fix) and the real orchestrator graph
— results below are genuine measurements, not placeholders. The one thing that can
still return a placeholder is `zero_shot_llm_call` / the LLM judge, and only when no
API key is configured for the selected model; each section below still says so
explicitly when that's the case.
        """
    )

st.divider()


# ============================================================================
# Sidebar — Step 1: Dataset setup
# ============================================================================

st.sidebar.header("Step 1 — Dataset setup")
st.sidebar.caption("Each dataset is downloaded once from its real GitHub repo (no manual steps).")

status = dataset_status()
for name, ready in status.items():
    st.sidebar.write(("✅ " if ready else "⬜ ") + name)

if st.sidebar.button("⬇️ Download missing datasets"):
    with st.spinner("Downloading datasets from GitHub..."):
        from eval.datasets import download_bugsinpy, download_patcheval, download_seccodeplt
        try:
            download_seccodeplt.download()
            log("Downloaded/verified SecCodePLT.")
        except Exception as e:
            log(f"SecCodePLT download issue: {e}")
        try:
            download_bugsinpy.download()
            log("Downloaded/verified BugsInPy.")
        except Exception as e:
            log(f"BugsInPy download issue: {e}")
        try:
            download_patcheval.download()
            log("Downloaded/verified PatchEval.")
        except Exception as e:
            log(f"PatchEval download issue: {e}")
    dataset_counts.clear()
    st.rerun()

st.sidebar.divider()


# ============================================================================
# Sidebar — Step 2: Sample selection
# ============================================================================

st.sidebar.header("Step 2 — Choose samples")
sampling_mode = st.sidebar.radio(
    "Sampling mode",
    ["Shared registry (recommended)", "Independent per-layer sampling"],
    help=(
        "Shared registry: every layer scores the SAME underlying examples, so you can "
        "compare 'agent right alone vs. pipeline wrong' per case. Independent: each "
        "layer samples on its own — faster to set up, but no per-case comparison."
    ),
)
use_shared = sampling_mode.startswith("Shared")

counts = dataset_counts()


def sample_slider(label: str, key: str, placeholder_max: int, default: int) -> int:
    """Slider capped at the dataset's real on-disk sample count. Falls back
    to a placeholder max (with a note) if the dataset hasn't been
    downloaded yet, so the slider still renders before Step 1 is done."""
    available = counts.get(key)
    if available is None:
        st.sidebar.caption(f"⬜ {label.split(' (')[0]} not downloaded yet — showing a placeholder range.")
        max_value = placeholder_max
    else:
        max_value = max(available, 2)
        st.sidebar.caption(f"{available} samples available on disk.")
    default_value = min(default, max_value)
    return st.sidebar.slider(label, 2, max_value, default_value, step=2)


n_seccodeplt = sample_slider("SecCodePLT samples (Security)", "seccodeplt", 100, 10)
n_bugsinpy = sample_slider("BugsInPy samples (Bug Detection)", "bugsinpy", 100, 10)
n_patcheval = sample_slider("PatchEval samples (Patch Generation)", "patcheval", 50, 10)
style_files_glob = st.sidebar.text_input(
    "Python files to lint (Style Agent), glob pattern",
    value="eval/*.py",
    help=(
        "The Style Agent isn't scored against a downloaded benchmark — it's scored "
        "against Pylint's own output on whatever Python files you point it at. Defaults "
        "to this harness's own top-level files as a small self-test (avoid recursive "
        "patterns like 'eval/**/*.py' — they'll also match the cloned dataset repos "
        "under eval/data/). Point this at your actual project's source for a real check."
    ),
)

st.sidebar.divider()


# ============================================================================
# Sidebar — Step 3: Choose models (judge + zero-shot baseline)
# ============================================================================

st.sidebar.header("Step 3 — Choose models")
st.sidebar.caption(
    "The judge grades Layer B/C output; the baseline is the single-prompt ablation Layer A "
    "compares agents against. Keep them different from each other (and from whichever model "
    "the agents under test run on) — grading with the same model that produced the answer "
    "biases the score toward what that model already believes."
)

PROVIDER_LABELS = {"anthropic": "Claude (Anthropic)", "deepseek": "DeepSeek", "openai": "OpenAI"}
_key_present = {
    "anthropic": api_key_configured("claude-opus-4-8"),
    "deepseek": api_key_configured("deepseek-v4-pro"),
    "openai": api_key_configured("gpt-4o"),
}


def model_picker(label: str, current_model: str, state_prefix: str) -> str:
    providers = list(AVAILABLE_MODELS)
    current_provider = next((p for p in providers if current_model in AVAILABLE_MODELS[p]), providers[0])
    provider = st.sidebar.selectbox(
        f"{label} — provider", providers, index=providers.index(current_provider),
        format_func=lambda p: f"{PROVIDER_LABELS[p]}{'' if _key_present[p] else ' — no API key set'}",
        key=f"{state_prefix}_provider",
    )
    models = AVAILABLE_MODELS[provider]
    default_model = current_model if current_model in models else models[0]
    model = st.sidebar.selectbox(
        f"{label} — model", models, index=models.index(default_model), key=f"{state_prefix}_model",
    )
    if not _key_present[provider]:
        st.sidebar.warning(
            f"No API key configured for {PROVIDER_LABELS[provider]} — this role will fall back to "
            "placeholder output until one is set in .env."
        )
    return model


judge_model = model_picker("Judge LLM", get_judge_model(), "judge")
baseline_model = model_picker("Baseline LLM", get_baseline_model(), "baseline")
os.environ["EVAL_HARNESS_JUDGE_MODEL"] = judge_model
os.environ["EVAL_HARNESS_BASELINE_MODEL"] = baseline_model

st.sidebar.divider()


# ============================================================================
# Sidebar — Step 4: Choose layers
# ============================================================================

st.sidebar.header("Step 4 — Choose what to run")
run_a = st.sidebar.checkbox("Layer A — Per-agent benchmarks", value=True)
run_b = st.sidebar.checkbox("Layer B — End-to-end PR review", value=True)
run_c = st.sidebar.checkbox("Layer C — Adversarial resistance", value=True)
run_gate = st.sidebar.checkbox("Apply release gate after running", value=True)

run_clicked = st.sidebar.button("▶️ Run evaluation", type="primary", use_container_width=True)

st.sidebar.caption(
    "Runs happen in this process — results are written to `results/*.json` exactly as "
    "the CLI would produce, and this page reads them back."
)


# ============================================================================
# Run logic
# ============================================================================

def do_run() -> None:
    st.session_state.run_log = []
    st.session_state.last_run_layers = []

    if use_shared:
        from eval.shared_cases import build_registry
        build_registry(n_seccodeplt=n_seccodeplt, n_bugsinpy=n_bugsinpy)
        log(f"Built shared registry: {n_seccodeplt} SecCodePLT + {n_bugsinpy} BugsInPy cases.")

    if run_a:
        from eval.runners import run_bug_eval, run_patch_eval, run_security_eval, run_style_eval
        st.session_state.last_run_layers.append("A")
        try:
            run_security_eval.run_seccodeplt(n=None if use_shared else n_seccodeplt, use_shared=use_shared)
            log("Layer A: Security Agent vs. SecCodePLT — done.")
        except Exception as e:
            log(f"Layer A Security run failed: {e}")
        try:
            run_bug_eval.run_bugsinpy(n=None if use_shared else n_bugsinpy, use_shared=use_shared)
            log("Layer A: Bug Detection Agent vs. BugsInPy — done.")
        except Exception as e:
            log(f"Layer A Bug Detection run failed: {e}")
        try:
            run_patch_eval.run_patcheval(n=n_patcheval)
            log("Layer A: Patch Agent vs. PatchEval — done.")
        except Exception as e:
            log(f"Layer A Patch (PatchEval) run failed: {e}")
        try:
            run_patch_eval.run_bugsinpy_patch(n=n_bugsinpy)
            log("Layer A: Patch Agent vs. BugsInPy patch pass rate — done.")
        except Exception as e:
            log(f"Layer A Patch (BugsInPy) run failed: {e}")
        try:
            import glob
            style_files = glob.glob(style_files_glob, recursive=True)
            if style_files:
                run_style_eval.run_pylint_agreement(style_files)
                run_style_eval.run_radon_spot_check(style_files)
                log(f"Layer A: Style Agent vs. Pylint/Radon on {len(style_files)} files — done.")
            else:
                log(f"Layer A: Style Agent skipped — no files matched '{style_files_glob}'.")
        except Exception as e:
            log(f"Layer A Style run failed: {e}")

    if run_b:
        from eval.e2e import build_pr_cases, run_e2e_review
        st.session_state.last_run_layers.append("B")
        try:
            if use_shared:
                build_pr_cases.build(use_shared=True)
            else:
                build_pr_cases.build(n_per_source=max(n_seccodeplt, n_bugsinpy) // 2 or 2)
            log("Layer B: built PR-shaped test cases (positive + clean).")
            run_e2e_review.run()
            log("Layer B: ran full pipeline + LLM judge on all cases.")
        except Exception as e:
            log(f"Layer B run failed: {e}")

    if run_c:
        from eval.e2e import build_adversarial_cases, run_adversarial_eval
        st.session_state.last_run_layers.append("C")
        try:
            build_adversarial_cases.build(n_source_samples=4, use_shared=use_shared)
            log("Layer C: built 4 adversarial (prompt-injection) test cases.")
            run_adversarial_eval.run()
            log("Layer C: ran full pipeline + judge on adversarial cases.")
        except Exception as e:
            log(f"Layer C run failed: {e}")

    from eval.report import aggregate_results
    aggregate_results.aggregate()
    log("Aggregated Layer A results into final_report.json / .md.")

    if run_gate:
        from eval.report import release_gate
        release_gate.run_gate()
        log("Applied the release gate to available results.")


if run_clicked:
    if not (run_a or run_b or run_c):
        st.sidebar.error("Select at least one layer to run.")
    else:
        with st.spinner("Running the evaluation harness..."):
            do_run()
        st.success("Run complete — see results below.")


# ============================================================================
# Run log
# ============================================================================

if st.session_state.run_log:
    with st.expander("🪵 Run log", expanded=False):
        for line in st.session_state.run_log:
            st.write("• " + line)

st.divider()


# ============================================================================
# Results — Layer A
# ============================================================================

st.header("Results")

final_report = load_json(RESULTS_DIR / "final_report.json")

st.subheader("Layer A — Per-agent benchmarks")
if not final_report or not final_report.get("records"):
    st.info("No Layer A results yet. Select Layer A and click **Run evaluation**.")
else:
    thresholds = CFG["thresholds"]
    cols = st.columns(len(final_report["records"]) or 1)
    for col, record in zip(cols, final_report["records"]):
        with col:
            st.markdown(f"**{record['benchmark']}**  \n_{record['agent']}, n={record['n']}_")
            metrics = record.get("metrics", {})
            headline = next((k for k in ("f1", "recall", "clean_pass_rate", "agreement") if k in metrics), None)
            if headline:
                target = metrics.get("target")
                metric_card(headline, metrics.get(headline), target, help_text=f"Raw metric from {record['benchmark']}")
            baseline = record.get("baseline_zero_shot", {})
            if baseline.get("f1") is not None:
                st.caption(f"Zero-shot baseline F1: {baseline['f1']:.3f} — the delta above is what the multi-agent system adds.")

    st.markdown("#### What these numbers mean")
    st.markdown(
        """
- **F1 / recall / pass rate** compares the agent's predictions to real, known-correct
  labels from the benchmark. Higher is better, but these benchmarks are intentionally
  hard (real CVEs, real bugs) — don't expect scores near 1.0.
  Note: BugsInPy's recall is currently a **proxy** (every example is a known bug, so
  precision on clean code isn't measured yet — see the harness's Known Limitations).
- **Zero-shot baseline** is the same test, run through one plain LLM call with no
  agent pipeline. The *gap* between the agent's score and this baseline is the actual
  argument for building a multi-agent system instead of one prompt.
- **Target** is the honest, benchmark-calibrated bar from `config.yaml` — not the
  original (inflated) proposal numbers.
        """
    )

st.divider()


# ============================================================================
# Results — Layer B
# ============================================================================

st.subheader("Layer B — End-to-end PR review quality")
e2e = load_json(RESULTS_DIR / "full_pipeline__llm-judge-e2e.json")
if not e2e:
    st.info("No Layer B results yet. Select Layer B and click **Run evaluation**.")
else:
    metrics = e2e.get("metrics", {})
    if metrics.get("n_judged", 0) == 0:
        st.warning(
            "⚠️ No cases were judged in this run (`n_judged` = 0) — these are placeholder "
            "zeros, not real quality scores. The judge itself (`eval/e2e/llm_judge.py`'s "
            "`_call_judge_llm`) is wired to a real model call; a 0 here means either no "
            "API key is configured for the selected judge model, or every judge call in "
            "this specific run failed to parse (see `n_parse_failures` in the raw JSON). "
            "Re-run the evaluation to get a current answer."
        )
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Positive cases** (real issue present — did it catch it?)")
            pos = metrics.get("positive_cases", {})
            for dim in ("coverage_mean", "noise_mean", "actionability_mean", "coherence_mean", "overall_mean"):
                st.write(f"- {dim.replace('_mean', '')}: **{pos.get(dim, '—')}** / 5")
        with c2:
            st.markdown("**Clean cases** (no real issue — did it stay quiet?)")
            clean = metrics.get("clean_cases_false_positive_check", {})
            for dim in ("coverage_mean", "noise_mean", "actionability_mean", "coherence_mean", "overall_mean"):
                st.write(f"- {dim.replace('_mean', '')}: **{clean.get(dim, '—')}** / 5")
        st.caption(
            "Positive and clean scores are never averaged together — a system can have "
            "strong detection while still crying wolf on clean code, or vice versa."
        )
    latency = metrics.get("pipeline_latency", {})
    if latency.get("n"):
        st.markdown(
            f"**Pipeline latency:** mean {latency['mean_s']}s · p50 {latency['p50_s']}s · "
            f"p95 {latency['p95_s']}s · max {latency['max_s']}s per PR review"
        )

st.divider()


# ============================================================================
# Results — Layer C
# ============================================================================

st.subheader("Layer C — Adversarial (prompt-injection) resistance")
adv = load_json(RESULTS_DIR / "full_pipeline__adversarial-injection.json")
if not adv:
    st.info("No Layer C results yet. Select Layer C and click **Run evaluation**.")
else:
    metrics = adv.get("metrics", {})
    if metrics.get("n_judged", 0) == 0:
        st.warning(
            "⚠️ No cases were judged in this run (`n_judged` = 0) — placeholder result, "
            "not a real resistance score. The judge is wired to a real model call; check "
            "that an API key is configured for the selected judge model, then re-run."
        )
    else:
        rate = metrics.get("resistance_rate")
        if rate is not None and rate < 1.0:
            st.error(
                f"🚨 Resistance rate: {rate} — {metrics['n_manipulated']}/{metrics['n_judged']} "
                "cases manipulated. Treat this as a security bug to fix, not a score to average."
            )
        elif rate is not None:
            st.success(f"✅ Resistance rate: {rate} — no cases manipulated.")
        by_type = metrics.get("by_attack_type", {})
        if by_type:
            st.write("By attack type:")
            for attack, res in by_type.items():
                st.write(f"- {attack}: {res['resistance_rate']} (n={res['n']})")

st.divider()


# ============================================================================
# Release gate
# ============================================================================

st.subheader("Release gate — go/no-go verdict")
gate = load_json(RESULTS_DIR / "release_gate.json")
if not gate:
    st.info("Run the release gate (checkbox in the sidebar) after running at least one layer.")
else:
    overall = gate.get("overall")
    color = {"PASS": "success", "FAIL": "error", "INCOMPLETE": "warning"}.get(overall, "info")
    getattr(st, color)(f"**Overall verdict: {overall}**")

    for check in gate.get("checks", []):
        icon = {"PASS": "✅", "FAIL": "❌", "SKIPPED": "⏭️"}.get(check["status"], "❓")
        st.write(f"{icon} **[{check['section']}]** {check['rule']} — {check['detail']}")

    st.caption(
        "Rules are declared in `eval/config.yaml`'s `release_gate` block, before results "
        "exist — so the bar can't be fit to whatever a run happens to produce."
    )

st.divider()


# ============================================================================
# Publish / download
# ============================================================================

st.subheader("📤 Publish results")
c1, c2, c3 = st.columns(3)
final_md = RESULTS_DIR / "final_report.md"
if final_md.exists():
    with c1:
        st.download_button("Download final_report.md", final_md.read_text(), file_name="final_report.md")
if (RESULTS_DIR / "final_report.json").exists():
    with c2:
        st.download_button(
            "Download final_report.json",
            (RESULTS_DIR / "final_report.json").read_text(),
            file_name="final_report.json",
        )
if gate:
    with c3:
        st.download_button(
            "Download release_gate.json",
            json.dumps(gate, indent=2),
            file_name="release_gate.json",
        )

if final_md.exists():
    with st.expander("View final_report.md"):
        st.markdown(final_md.read_text())
