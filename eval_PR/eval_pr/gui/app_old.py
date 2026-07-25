"""eval_PR GUI — Streamlit app.

A guided interface for auditing one real PR: explains what the tool does,
accepts the PR and Fixed Code as either uploaded files or pasted text,
runs the real audit logic (not a mock), and renders the verdict and full
report with plain-language explanations.

Run with:
    pip install -r requirements.txt
    streamlit run eval_pr/gui/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

EVAL_PR_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(EVAL_PR_ROOT))

from eval_pr.config import BASELINE_MODEL, JUDGE_MODEL, api_key_configured  # noqa: E402
from eval_pr.judge import ATTACK_CATEGORIES, CATEGORIES  # noqa: E402
from eval_pr.run_single_pr import audit, render_markdown  # noqa: E402

st.set_page_config(page_title="eval_PR — Single PR Audit", page_icon="🔍", layout="wide")

if "result" not in st.session_state:
    st.session_state.result = None
if "pr_label" not in st.session_state:
    st.session_state.pr_label = "PR"


# ============================================================================
# Header
# ============================================================================

st.title("🔍 eval_PR — Single Real-PR Audit")
st.markdown(
    "Audit **one specific pull request** your multi-agent code-review system has "
    "already fully processed. You provide the original PR and the system's actual "
    "Fixed Code; an independent judge checks whether every issue was really found "
    "and fixed, whether the review held up against manipulation attempts, and how it "
    "compares to a simple single-prompt baseline — then gives you a clear **GO / NO-GO**."
)

with st.expander("📖 How this works", expanded=False):
    st.markdown(
        """
**Inputs — both must already exist, this tool does not run your pipeline:**
1. **The original PR** — the code as submitted.
2. **The Fixed Code** — what your system actually produced for it: the Security,
   Bug, Style, and Performance agents' findings, the generated patch, and test results.

**What the judge checks, in one independent audit:**
- **Per category** (Security / Bug / Style / Performance): what issues really exist,
  what got patched, what still remains — determined independently, not by trusting
  the agents' own claims.
- **Quality rubric (1–5):** coverage, noise, actionability, coherence, overall — scored
  for your system *and* for a zero-shot baseline (one plain LLM call, no agents), so
  you can see what the multi-agent approach actually adds.
- **Adversarial resistance:** checked against 4 known manipulation patterns
  (instruction override, role confusion, fake verdict injection, output suppression),
  plus a separate check that the final patched code itself carries no adversarial content.

**The verdict is computed by fixed rules, not left to the model's opinion:**
NO-GO if any category still has a remaining issue, any detected attack wasn't resisted,
the Fixed Code itself is still adversarial, or the patch scores 1/5 on actionability
(broken/non-functional). GO otherwise.
        """
    )

# API key / model status
if api_key_configured():
    st.success(f"✅ API key configured — judge model: `{JUDGE_MODEL}` · baseline model: `{BASELINE_MODEL}`")
else:
    st.warning(
        "⚠️ No `ANTHROPIC_API_KEY` configured — audits will run in **placeholder mode** "
        "(the tool works end-to-end, but results won't be real). Set the environment "
        "variable and restart to get real audits."
    )

st.divider()


# ============================================================================
# Input
# ============================================================================

st.header("1. Provide the PR and its Fixed Code")

input_mode = st.radio("Input method", ["Upload files", "Paste text"], horizontal=True)

pr_text, fixed_output_text, pr_label = "", "", "PR"

if input_mode == "Upload files":
    col1, col2 = st.columns(2)
    with col1:
        pr_file = st.file_uploader("Original PR", type=None, help="Any text file containing the PR diff or code")
        if pr_file:
            pr_text = pr_file.read().decode("utf-8", errors="replace")
            pr_label = pr_file.name
    with col2:
        fixed_output_file = st.file_uploader(
            "Fixed Code", type=None,
            help="Any text/JSON file containing your system's agent findings + patch + test results",
        )
        if fixed_output_file:
            fixed_output_text = fixed_output_file.read().decode("utf-8", errors="replace")
else:
    col1, col2 = st.columns(2)
    with col1:
        pr_text = st.text_area("Original PR", height=300, placeholder="Paste the PR diff or code here...")
    with col2:
        fixed_output_text = st.text_area(
            "Fixed Code", height=300,
            placeholder="Paste the system's findings + patch + test results here...",
        )

run_clicked = st.button("▶️ Run Audit", type="primary", use_container_width=True)

st.divider()


# ============================================================================
# Run
# ============================================================================

if run_clicked:
    if not pr_text.strip() or not fixed_output_text.strip():
        st.error("Both the PR and the Fixed Code are required.")
    else:
        with st.spinner("Auditing... this calls the judge model and the zero-shot baseline model."):
            try:
                result = audit(pr_text, fixed_output_text)
                st.session_state.result = result
                st.session_state.pr_label = pr_label
            except Exception as e:
                st.error(f"Audit failed: {e}")
                st.session_state.result = None


# ============================================================================
# Results
# ============================================================================

result = st.session_state.result
if result is None:
    st.info("Provide a PR and Fixed Code above, then click **Run Audit** to see results here.")
else:
    m = result["metrics"]

    st.header("2. Results")

    if result.get("is_placeholder"):
        st.warning(
            "⚠️ **Placeholder result** — no real model call succeeded (no API key, or the "
            "call failed). This demonstrates the tool's output shape, not a real audit."
        )

    # --- Verdict banner ---
    if m["verdict"] == "GO":
        st.success("## ✅ GO")
    else:
        st.error("## ❌ NO-GO")
        st.markdown("**Reasons:**")
        for r in m["verdict_reasons"]:
            st.markdown(f"- {r}")

    st.caption(
        "The verdict is computed by fixed rules from the findings below — the model never "
        "declares it itself."
    )

    # --- Categorical findings ---
    st.subheader("Categorical findings")
    cat_cols = st.columns(4)
    status_icon = {"resolved": "✅", "unresolved": "❌", "none_found": "⚪"}
    for col, cat in zip(cat_cols, CATEGORIES):
        c = m[cat]
        status = m["category_status"][cat]
        with col:
            st.markdown(f"**{cat.capitalize()}** {status_icon[status]}")
            st.caption(status)
            with st.expander("Details"):
                st.markdown(f"**Identified:** {', '.join(c['identified']) or '(none)'}")
                st.markdown(f"**Patched:** {', '.join(c['patched']) or '(none)'}")
                st.markdown(f"**Remaining:** {', '.join(c['remaining']) or '(none)'}")

    st.divider()

    # --- Rubric comparison ---
    st.subheader("Quality rubric — this system vs. a zero-shot baseline")
    rubric, baseline, delta = m["rubric"], m["baseline_rubric"], m.get("rubric_delta_vs_baseline")
    rubric_rows = []
    for dim in ("coverage", "noise", "actionability", "coherence", "overall"):
        rubric_rows.append({
            "Dimension": dim.capitalize(),
            "System": rubric.get(dim, "—"),
            "Baseline": baseline.get(dim, "—"),
            "Delta": delta[dim] if delta else "—",
        })
    st.table(rubric_rows)
    if not delta:
        st.caption("Delta not shown — one or both rubric scores are still placeholders.")
    st.caption(
        "The baseline never affects the verdict — it's shown only as evidence of what the "
        "multi-agent architecture adds over a single plain LLM call on this PR."
    )

    st.divider()

    # --- Adversarial resistance ---
    st.subheader("Adversarial resistance (4 attack categories)")
    rate = m["resistance_rate"]
    if rate is None:
        st.info("No attack pattern detected in this PR — resistance rate not applicable.")
    elif rate < 1.0:
        st.error(f"Resistance rate: {rate} — at least one detected attack was not resisted.")
    else:
        st.success(f"Resistance rate: {rate} — all detected attacks were resisted.")

    adv_rows = []
    for attack in ATTACK_CATEGORIES:
        a = m["adversarial"][attack]
        adv_rows.append({
            "Attack category": attack.replace("_", " "),
            "Detected": a["detected"],
            "Resisted": a["resisted"],
            "Rationale": a["rationale"],
        })
    st.table(adv_rows)

    if m["fixed_output_contains_adversarial_content"]:
        st.error(f"🚨 Fixed Code itself still contains adversarial content — {m['fixed_output_adversarial_rationale']}")
    else:
        st.success("✅ Fixed Code itself is clean of adversarial content.")

    st.divider()

    # --- Summary ---
    st.subheader("Judge's summary")
    st.write(m.get("summary_rationale") or "(not provided)")

    st.divider()

    # --- Publish / download ---
    st.subheader("📤 Publish results")
    md_report = render_markdown(result, pr_label=st.session_state.pr_label)
    import json as _json
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("Download report (.md)", md_report, file_name="eval_pr_audit.md")
    with c2:
        st.download_button("Download result (.json)", _json.dumps(result, indent=2), file_name="eval_pr_audit.json")

    with st.expander("View full markdown report"):
        st.markdown(md_report)
