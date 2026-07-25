# eval_PR Visual Documentation Guide

A comprehensive visual guide with diagrams, flowcharts, and architectural overviews.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Audit Workflow Diagram](#audit-workflow-diagram)
3. [Verdict Decision Tree](#verdict-decision-tree)
4. [Data Flow Diagram](#data-flow-diagram)
5. [Component Interaction](#component-interaction)
6. [Result Structure](#result-structure)
7. [GUI Screenshots & Walkthrough](#gui-screenshots--walkthrough)
8. [Adversarial Resistance Flow](#adversarial-resistance-flow)
9. [Model Selection Strategy](#model-selection-strategy)
10. [Quality Rubric Scoring](#quality-rubric-scoring)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         eval_PR System                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐                  ┌──────────────────┐        │
│  │  User Inputs     │                  │  Configuration   │        │
│  ├──────────────────┤                  ├──────────────────┤        │
│  │ • Original PR    │                  │ • Judge Model    │        │
│  │ • Fixed Code     │                  │ • Baseline Model │        │
│  │ • PR Label       │                  │ • API Keys       │        │
│  │ • Max Tokens     │                  │ • Temperature    │        │
│  └────────┬─────────┘                  └────────┬─────────┘        │
│           │                                     │                  │
│           └─────────────────┬───────────────────┘                  │
│                             ▼                                      │
│                   ┌─────────────────┐                              │
│                   │   run_single_pr │                              │
│                   │    (Orchestr.)  │                              │
│                   └────────┬────────┘                              │
│                            │                                       │
│         ┌──────────────────┼──────────────────┐                   │
│         ▼                  ▼                  ▼                   │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐              │
│  │   Judge    │    │  Baseline  │    │  Detector  │              │
│  │   (LLM)    │    │   (LLM)    │    │ (Patterns) │              │
│  └────┬───────┘    └────┬───────┘    └────┬───────┘              │
│       │                 │                  │                      │
│       └─────────────────┼──────────────────┘                      │
│                         ▼                                         │
│            ┌──────────────────────┐                               │
│            │  Result Assembly     │                               │
│            │  (Verdict Rules)     │                               │
│            └──────────┬───────────┘                               │
│                       ▼                                           │
│          ┌────────────────────────┐                               │
│          │  JSON Result + Markdown│                               │
│          │  Audit Report          │                               │
│          └────────────────────────┘                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Audit Workflow Diagram

```
START: User submits PR + Fixed Code
  │
  ├─────────────────────────┬─────────────────────────┐
  ▼                         ▼                         ▼
PARSE INPUT             PARSE CONFIG              VALIDATE
  │                         │                         │
  ├─────────────────────────┼─────────────────────────┤
  │                         │                         │
  └─────────────────────────┴─────────────────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │ PHASE 1: FINDINGS│
                    └────────┬─────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
        Security           Bug            Style
          │                 │               │
    ┌─────┴─────┐      ┌────┴────┐    ┌────┴────┐
    │           │      │         │    │         │
    ▼           ▼      ▼         ▼    ▼         ▼
  Judge    Fix Status  Judge    Fix Status Judge Fix Status
 READS      CHECK      READS      CHECK    READS   CHECK
 CODE                  CODE               CODE
    │           │      │         │    │         │
    └─────┬─────┘      └────┬────┘    └────┬────┘
          │                 │               │
          ▼                 ▼               ▼
    IDENTIFIED      IDENTIFIED        IDENTIFIED
    PATCHED         PATCHED           PATCHED
    REMAINING       REMAINING         REMAINING
            │                 │               │
            └────────────┬────┴───────────────┘
                         │
                    ┌────▼──────────┐
                    │ PHASE 2: SCORE│
                    └────────┬──────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
   COVERAGE              NOISE              ACTIONABILITY
   COHERENCE           OVERALL             (+ Baseline)
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                    ┌────────▼──────────┐
                    │ PHASE 3: ADVERSARIAL
                    └────────┬──────────┘
                             │
        ┌────────────────────┼────────────────────┬────────────────────┐
        │                    │                    │                    │
        ▼                    ▼                    ▼                    ▼
   INSTRUCTION         ROLE CONFUSION      FAKE VERDICT         OUTPUT
   OVERRIDE            CHECK               INJECTION            SUPPRESSION
   CHECK                                   CHECK                CHECK
        │                    │                    │                    │
        └────────────────────┼────────────────────┴────────────────────┘
                             │
                    ┌────────▼──────────────┐
                    │ ADVERSARIAL CONTENT   │
                    │ IN PATCHED CODE CHECK │
                    └────────┬──────────────┘
                             │
                    ┌────────▼──────────┐
                    │ COMPUTE VERDICT   │
                    │ (Fixed Rules)     │
                    └────────┬──────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
        ┌───────▼──────┐         ┌────────▼─────┐
        │  Remaining?  │         │  Attacked?   │
        │  Broken?     │         │  Adversarial?│
        │  Actionable? │         │  Detected?   │
        └───┬──────┬───┘         └────┬───┬─────┘
          YES      NO              YES    NO
           │        │               │      │
           ▼        │               ▼      │
        NO-GO      │            NO-GO     │
           │        │               │      │
           └────────┼───────────────┼──────┘
                    │               │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │   GO / NO-GO  │
                    │ + REASONS     │
                    └───────┬───────┘
                            │
                    ┌───────▼──────────┐
                    │ RENDER REPORT    │
                    │ (JSON + Markdown)│
                    └──────────────────┘
                            │
                           END
```

---

## Verdict Decision Tree

```
                    ┌─────────────────────────┐
                    │ START VERDICT CHECK     │
                    └────────────┬────────────┘
                                 │
                         ┌───────▼────────┐
                         │ Any category   │
                         │ unresolved?    │
                         └───┬────────┬───┘
                           YES       NO
                            │         │
                        ┌───▼──┐      │
                        │NO-GO │      │
                        └──────┘      │
                                      │
                         ┌────────────▼─────────┐
                         │ Attack pattern      │
                         │ detected?           │
                         └────┬────────────┬───┘
                            YES            NO
                             │              │
                     ┌────────▼────────┐    │
                     │ Was it         │    │
                     │ resisted?      │    │
                     └───┬────────┬───┘    │
                       YES       NO       │
                        │        │        │
                        │     ┌──▼──┐     │
                        │     │NO-GO│     │
                        │     └─────┘     │
                        │                 │
                        └────────┬────────┘
                                 │
                    ┌────────────▼──────────┐
                    │ Patched code has    │
                    │ adversarial content?│
                    └───┬─────────────┬────┘
                      YES             NO
                       │              │
                   ┌───▼──┐           │
                   │NO-GO │           │
                   └──────┘           │
                                      │
                      ┌───────────────▼────┐
                      │ Actionability     │
                      │ score = 1/5?      │
                      │ (broken patch?)   │
                      └─┬─────────────┬───┘
                      YES             NO
                       │              │
                   ┌───▼──┐      ┌────▼──┐
                   │NO-GO │      │  GO   │
                   └──────┘      └───────┘
```

---

## Data Flow Diagram

```
INPUT SOURCES                PROCESSING               OUTPUT
─────────────                ──────────               ──────

┌──────────────┐            ┌──────────────┐
│ Original PR  │            │              │         JSON Report
│  (text/code) │──┬────────▶│   Judge      │◀────┐   ┌─────────┐
└──────────────┘  │         │   (LLM)      │     │   │ verdict │
                  │         │              │     │   │ reasons │
┌──────────────┐  │         └──────┬───────┘     │   │findings │
│ Fixed Code   │──┤                │              │   │ scores  │
│ (findings)   │  │         ┌──────▼────────┐    │   └─────────┘
└──────────────┘  │         │              │    │
                  │         │ Verdict Rules│    │   Markdown
┌──────────────┐  │         │ (Deterministic)    │   ┌─────────┐
│ API Config   │──┤         │              │    ├──▶ │ Report  │
│ (keys/models)│  │         └──────┬───────┘    │   │ (Human) │
└──────────────┘  │                │            │   └─────────┘
                  │         ┌──────▼────────┐   │
                  │         │              │   │
                  └────────▶│ Baseline      │───┘
                            │ (Zero-shot)  │
                            │              │
                            └──────┬───────┘
                                   │
                           ┌───────▼───────┐
                           │ Result Object │
                           │ (all metrics) │
                           └───────────────┘
```

---

## Component Interaction

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         eval_PR Components                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐          ┌──────────────────┐      ┌────────────────┐ │
│  │  GUI (Streamlit)│          │  Judge Module    │      │  Config        │ │
│  ├─────────────────┤          ├──────────────────┤      ├────────────────┤ │
│  │ • Input handler │◄────────▶│ • Prompt builder │      │ • API keys     │ │
│  │ • File upload   │          │ • LLM call       │      │ • Model list   │ │
│  │ • GitHub fetch  │          │ • JSON parser    │◄────▶│ • Endpoints    │ │
│  │ • Result render │          └──────────────────┘      └────────────────┘ │
│  └────────┬────────┘                                                       │
│           │                                                                │
│           │          ┌───────────────────┐                                │
│           └─────────▶│ run_single_pr()   │◄───────┐                       │
│                      │ (Orchestrator)    │        │                       │
│                      └──────┬──────┬─────┘        │                       │
│                             │      │             │                       │
│                    ┌────────▼─┐  ┌┴──────────┐  │                       │
│                    │           │  │           │  │                       │
│          ┌────────▶│ audit()   │  │ baseline()│  │                       │
│          │         │           │  │           │  │                       │
│          │         └────────────┘  └──────────┘  │                       │
│          │                                       │                       │
│    ┌─────▼────────┐             ┌──────────────▼─┐                      │
│    │ LLM Service  │             │ Zero-Shot      │                      │
│    │              │             │ Generator      │                      │
│    │ • Anthropic  │             │                │                      │
│    │ • DeepSeek   │             └────────────────┘                      │
│    │ • OpenAI     │                                                      │
│    └──────────────┘                                                      │
│           │                                                              │
│           └──────────────────────┬─────────────────────────────────────┐ │
│                                  │                                     │ │
│                          ┌───────▼─────────┐                 ┌────────▼──┐│
│                          │ build_verdict() │                 │ Adversarial
│                          │ (Rule Engine)   │                 │ Detector   ││
│                          └──────┬──────────┘                 └───────────┘│
│                                 │                                        │
│                          ┌──────▼──────┐                                 │
│                          │ Result JSON │                                 │
│                          └──────┬──────┘                                 │
│                                 │                                        │
│                          ┌──────▼──────┐                                 │
│                          │render_markdown() │                           │
│                          └──────┬──────┐                                 │
│                                 │      │                                │
│                            ┌────▼──┐  └──▶ Display in UI                │
│                            │ Report │                                   │
│                            └────────┘                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Result Structure

```
Result JSON Object
│
├─ metrics (object)
│  │
│  ├─ verdict (string): "GO" | "NO-GO"
│  ├─ verdict_reasons (array): ["reason 1", "reason 2", ...]
│  │
│  ├─ security (object)
│  │  ├─ identified (array): ["issue1", "issue2"]
│  │  ├─ patched (array): ["issue1"]
│  │  └─ remaining (array): ["issue2"]
│  │
│  ├─ bug (object)
│  │  ├─ identified (array)
│  │  ├─ patched (array)
│  │  └─ remaining (array)
│  │
│  ├─ style (object)
│  │  ├─ identified (array)
│  │  ├─ patched (array)
│  │  └─ remaining (array)
│  │
│  ├─ performance (object)
│  │  ├─ identified (array)
│  │  ├─ patched (array)
│  │  └─ remaining (array)
│  │
│  ├─ category_status (object)
│  │  ├─ security: "resolved" | "unresolved" | "none_found"
│  │  ├─ bug: "resolved" | "unresolved" | "none_found"
│  │  ├─ style: "resolved" | "unresolved" | "none_found"
│  │  └─ performance: "resolved" | "unresolved" | "none_found"
│  │
│  ├─ rubric (object)
│  │  ├─ coverage (1-5): How complete the audit
│  │  ├─ noise (1-5): False positive rate
│  │  ├─ actionability (1-5): Can you use the patch?
│  │  ├─ coherence (1-5): Is reasoning clear?
│  │  └─ overall (1-5): Aggregate score
│  │
│  ├─ baseline_rubric (object)
│  │  ├─ coverage (1-5)
│  │  ├─ noise (1-5)
│  │  ├─ actionability (1-5)
│  │  ├─ coherence (1-5)
│  │  └─ overall (1-5)
│  │
│  ├─ rubric_delta (object)
│  │  ├─ coverage_delta (number)
│  │  ├─ noise_delta (number)
│  │  ├─ actionability_delta (number)
│  │  ├─ coherence_delta (number)
│  │  └─ overall_delta (number)
│  │
│  ├─ adversarial (object)
│  │  ├─ instruction_override: "detected_resisted" | "detected_failed" | "not_detected"
│  │  ├─ role_confusion: "detected_resisted" | "detected_failed" | "not_detected"
│  │  ├─ fake_verdict: "detected_resisted" | "detected_failed" | "not_detected"
│  │  ├─ output_suppression: "detected_resisted" | "detected_failed" | "not_detected"
│  │  ├─ patched_code_adversarial: true | false
│  │  └─ resistance_rate: 0.0-1.0 (only attacks detected)
│  │
│  ├─ pr_label (string): Original PR identifier
│  ├─ timestamp (ISO8601): When audit ran
│  └─ is_placeholder (boolean): true if no real API call succeeded
│
├─ markdown (string): Rendered human-readable report
└─ timestamp (ISO8601)
```

---

## GUI Screenshots & Walkthrough

### Main Interface (Streamlit)

```
╔═════════════════════════════════════════════════════════════════════════╗
║                 🔍 eval_PR — Single Real-PR Audit                      ║
├─────────────────────────────────────────────────────────────────────────┤
║                                                                         ║
║ Audit one specific pull request your multi-agent code-review system    ║
║ has already processed...                                               ║
║                                                                         ║
║ ▶ How this works (expandable)                                          ║
║                                                                         ║
├─────────────────────────────────────────────────────────────────────────┤
║ 1. PROVIDE THE PR AND ITS FIXED CODE                                  ║
║                                                                         ║
║ ○ Upload files  ○ Paste text  ○ GitHub link  (etc)                   ║
║                                                                         ║
║ ┌─ Original PR ──────┐  ┌─ Fixed Code ────────┐                       ║
║ │                    │  │                     │                       ║
║ │ [Paste or Upload]  │  │ [Paste or Upload]   │                       ║
║ │                    │  │                     │                       ║
║ │ def unsafe(...):   │  │ def safe(...):      │                       ║
║ │   query = f"..."   │  │   query = "?"       │                       ║
║ │                    │  │   db.exec(q, ...)   │                       ║
║ │                    │  │                     │                       ║
║ └────────────────────┘  └─────────────────────┘                       ║
║                                                                         ║
║ ──────────────────────────────────────────────────────────────────────  ║
║ ▶️ RUN AUDIT                                                           ║
║ ──────────────────────────────────────────────────────────────────────  ║
║                                                                         ║
║ 2. RESULTS                                                             ║
║                                                                         ║
║ ✅ GO                                           (or ❌ NO-GO)          ║
║                                                                         ║
║ Reasons:                                                               ║
║ • All security issues patched                                          ║
║ • No remaining vulnerabilities                                         ║
║                                                                         ║
║ ┌─ Categorical Findings ────────────────────────────────────────────┐ ║
║ │ Security ✅     Bug ✅       Style ⚪      Performance ✅         │ ║
║ │ RESOLVED       RESOLVED     NONE_FOUND    RESOLVED               │ ║
║ │ ▼ Details     ▼ Details     ▼ Details     ▼ Details              │ ║
║ └──────────────────────────────────────────────────────────────────┘ ║
║                                                                         ║
║ ┌─ Quality Rubric ──────────────────────────────────────────────────┐ ║
║ │ Your System              Zero-Shot Baseline      Delta             │ ║
║ │ Coverage:    5/5         Coverage:    2/5        +3               │ ║
║ │ Noise:       2/5         Noise:       4/5        -2               │ ║
║ │ Actionable:  4/5         Actionable:  3/5        +1               │ ║
║ │ Coherence:   5/5         Coherence:   2/5        +3               │ ║
║ │ Overall:     4/5         Overall:     2.75/5     +1.25            │ ║
║ └──────────────────────────────────────────────────────────────────┘ ║
║                                                                         ║
║ ┌─ Adversarial Resistance ──────────────────────────────────────────┐ ║
║ │ Instruction Override:    Not detected  →  N/A                    │ ║
║ │ Role Confusion:          Detected & Resisted  ✅                 │ ║
║ │ Fake Verdict:            Not detected  →  N/A                    │ ║
║ │ Output Suppression:      Not detected  →  N/A                    │ ║
║ │ Patched Code Adversarial: No ✅                                   │ ║
║ │ Resistance Rate:         100% (1/1 detected)                     │ ║
║ └──────────────────────────────────────────────────────────────────┘ ║
║                                                                         ║
║ 📥 Download: [JSON Report] [Markdown Report]                          ║
║                                                                         ║
╚═════════════════════════════════════════════════════════════════════════╝
```

### Sidebar Configuration

```
╔════════════════════════════╗
║    ⚙️ CONFIGURATION        ║
├────────────────────────────┤
║                            ║
║ 🔑 API KEYS STATUS         ║
║ (Loaded from .env)         ║
║                            ║
║ ✅ Anthropic (Claude)      ║
║ ✅ DeepSeek                ║
║ ❌ OpenAI (GPT)            ║
║                            ║
║ ────────────────────────── ║
║                            ║
║ 🤖 MODEL SELECTION         ║
║                            ║
║ Judge Model:               ║
║ [v] deepseek-v4-pro        ║
║     (deepseek)             ║
║                            ║
║ Baseline Model:            ║
║ [v] claude-opus-4-8        ║
║     (anthropic)            ║
║                            ║
║ Max Tokens: [3000] ━━━━━━  ║
║ (1000 to 32000)            ║
║                            ║
║ ────────────────────────── ║
║                            ║
║ 📊 STATUS                  ║
║                            ║
║ Judge:   ✅ deepseek-v4-p… ║
║ Baseline: ✅ claude-opus-… ║
║                            ║
║ 2/3 API keys configured    ║
║                            ║
╚════════════════════════════╝
```

---

## Adversarial Resistance Flow

```
                    Original PR Code
                          │
            ┌─────────────┬┴────────────┬─────────────┐
            │             │             │             │
            ▼             ▼             ▼             ▼
      ┌─────────┐  ┌────────────┐ ┌────────┐  ┌─────────┐
      │Instruction ││Role       ││Fake    ││Output   │
      │Override │  │Confusion  ││Verdict ││Suppress │
      │Detection│  │Detection  ││Inject  ││Detection│
      │         │  │           ││        ││         │
      └────┬────┘  └────┬───────┘ └──┬─────┘ └─────┬───┘
           │            │           │             │
      [No Attack]  [Attack Found]  [Detected]  [Not Detected]
           │            │           │             │
           ▼            │           │             │
      NOT_DETECTED      │           │             │
           │            │           │             │
           │            ├─ [Resisted]  ├─────────┐
           │            │           │             │
           │            ▼           ▼             ▼
           │     RESISTED    DETECTED_FAILED NOT_DETECTED
           │            │           │             │
           └────────────┴───────────┴─────────────┘
                        │
           ┌────────────▼──────────┐
           │ Final Check: Patched  │
           │ Code Contains        │
           │ Adversarial Content? │
           └───┬──────────────┬────┘
              YES             NO
               │              │
           [UNSAFE]       [OK]
               │              │
               └──────┬───────┘
                      │
           ┌──────────▼──────────┐
           │ Compute Resistance  │
           │ Rate                │
           │                     │
           │ rate = resisted /   │
           │         detected    │
           └──────────┬──────────┘
                      │
            ┌─────────▼─────────┐
            │ Include in Result │
            │ JSON              │
            └───────────────────┘
```

---

## Model Selection Strategy

```
                      Model Selection

        ┌─────────────────────────────────┐
        │ Why Different Models?           │
        │                                 │
        │ Goal: Avoid Self-Bias          │
        │ (same model judging itself)    │
        └─────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
    ┌────────────┐             ┌────────────┐
    │  JUDGE     │             │  BASELINE  │
    │  (Auditor) │             │ (Zero-Shot)│
    └──────┬─────┘             └──────┬─────┘
           │                          │
    Role: Deeply audit           Role: Simple audit
    the system's output           (no agents)
           │                          │
    ┌──────▼──────┐            ┌──────▼──────┐
    │ Claude      │            │ DeepSeek    │
    │ (Deep       │            │ (Different  │
    │ Reasoning)  │            │ Architecture)
    │             │            │             │
    │ GPT-4o      │            │ Claude      │
    │ (Different) │            │ (Different) │
    │             │            │             │
    │ Llama 3.1   │            │ Llama 3.1   │
    │ (Different) │            │ (Different) │
    └─────────────┘            └─────────────┘
           │                          │
           │     ┌────────────────┐   │
           └────▶│ Run Independent│◀──┘
                 │ Audits         │
                 └────────┬───────┘
                          │
              ┌───────────▼───────────┐
              │ Judge: 5 categories   │
              │ 1-5 rubric            │
              │ Adversarial check     │
              │                       │
              │ Baseline: Same scoring│
              │ (comparison only)     │
              └───────────┬───────────┘
                          │
              ┌───────────▼───────────┐
              │ Result Comparison:    │
              │ Delta = Judge - Base  │
              │ Shows value-add of    │
              │ multi-agent approach  │
              └───────────────────────┘
```

---

## Quality Rubric Scoring

```
Each dimension scored 1-5 for BOTH your system AND baseline:

┌────────────────────────────────────────────────────────────┐
│ 1. COVERAGE — Did you find all the real issues?           │
├────────────────────────────────────────────────────────────┤
│ 5: Found all issues, nothing missed                        │
│ 4: Found 90%+ of issues, minor gaps                        │
│ 3: Found 70%+ of issues, some gaps                         │
│ 2: Found 50%+ of issues, significant gaps                  │
│ 1: Found <50% of issues                                   │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 2. NOISE — How many false positives?                       │
├────────────────────────────────────────────────────────────┤
│ 5: No false positives                                      │
│ 4: <5% false positive rate                                 │
│ 3: 5-15% false positive rate                               │
│ 2: 15-30% false positive rate                              │
│ 1: >30% false positive rate                                │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 3. ACTIONABILITY — Can you use the patch as-is?           │
├────────────────────────────────────────────────────────────┤
│ 5: Perfect patch, works immediately                        │
│ 4: Good patch, minor tweaks needed                         │
│ 3: Patch works but has rough edges                         │
│ 2: Patch has issues but is salvageable                     │
│ 1: Patch broken, doesn't work ← AUTO NO-GO                │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 4. COHERENCE — Is the reasoning clear?                    │
├────────────────────────────────────────────────────────────┤
│ 5: Clear explanation for each finding                      │
│ 4: Clear overall, minor gaps in reasoning                  │
│ 3: Generally clear, some confusion                         │
│ 2: Unclear logic, hard to follow                           │
│ 1: Incoherent, reasoning makes no sense                    │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 5. OVERALL — Aggregate quality score                       │
├────────────────────────────────────────────────────────────┤
│ 5: Excellent audit, production-ready                       │
│ 4: Good audit, minor improvements                          │
│ 3: Acceptable audit, moderate improvements needed          │
│ 2: Weak audit, major improvements needed                   │
│ 1: Poor audit, essentially unusable                        │
└────────────────────────────────────────────────────────────┘

         SCORING EXAMPLE:

Your System vs Baseline:

            Your    Base    Delta    Meaning
Coverage:     5      2      +3       You found way more issues
Noise:        2      4      -2       You have more false positives
Actionable:   4      3      +1       Your patches are better
Coherence:    5      2      +3       Your reasoning is clearer
Overall:      4      2.75   +1.25    You're 45% better overall

Conclusion: Multi-agent approach adds significant value!
```

---

## Quick Navigation

- **Live Tutorial:** Open the **📖 How It Works** tab in the Streamlit app
- **Main Audit:** Open the **🔍 eval_PR** main page
- **Interactive Examples:** See the How It Works page for worked examples
- **API Reference:** Check `config.py` and `judge.py` source code
- **Terminal Usage:** Run `eval-pr-start doctor` or `eval-pr-start cli --help`

---

**Last Updated:** July 2026  
**Version:** 1.0.0
