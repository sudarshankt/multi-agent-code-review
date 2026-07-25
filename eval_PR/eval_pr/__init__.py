"""eval_PR — single real-PR audit tool for a multi-agent code-review system.

Given a PR and the fixed output your system already produced for it (agent
findings, patch, and test results), an independent LLM judge audits both
files and produces one report: per-category issue findings, a 1-5 quality
rubric compared against a zero-shot baseline, and adversarial-resistance
checks across four attack patterns. A deterministic GO/NO-GO verdict is
computed from that report.

See README.md for setup and usage, SPEC.md for the full design.
"""

__version__ = "1.0.0"
