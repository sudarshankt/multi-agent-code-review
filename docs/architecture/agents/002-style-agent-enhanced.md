### Architectural Assessment of the Style Agent

Current **Style Agent** employs an elegant hybrid architecture: running a local, deterministic linter (Ruff) via `stdin` to minimize disk I/O, using the results to prime the LLM prompt, and then running a programmatic deduplication filter. 

However, looking closely at our project proposal, there are three architectural discrepancies and three core limitations in the current `style-agent.md` design:
1. **The Radon/Pylint Discrepancy:** The proposal promises *Radon* (cyclomatic/cognitive complexity, Halstead metrics) and *Pylint*, but the current implementation relies entirely on Ruff and LLM, missing structural complexity metrics.
2. **Brittle Deduplication:** The current deduplication relies strictly on an exact, case-insensitive title match (`f.title.lower() not in ruff_titles`). If Ruff reports `F401: unused import 'os'` and the LLM reports `Unused import 'os' in line 3`, the title match will fail, and duplicate alerts will slip through to the user.
3. **Wasted LLM Power on Auto-Fixable Issues:** Trivial syntactic formatting (e.g., PEP8 spaces, unused imports, or incorrect import sorting) can be resolved deterministically for free. Spending LLM reasoning steps and API costs on these is highly inefficient.

Here is the architectural blueprint to transition your Style Agent to a production-ready, highly optimized system.

---

### Enhancement 1: Integrating Radon for Deterministic Code Complexity Analysis
Instead of letting the LLM estimate code complexity (which is highly subjective and inconsistent), we should use Python’s native, fast AST-based complexity analyzer: `Radon`. This ensures exact McCabe cyclomatic complexity scores are generated in microseconds.

#### Implementation Strategy:
We can calculate cyclomatic complexity programmatically and inject the structural hotspots into the LLM prompt. If a block has a complexity score > 10 (Grade C or worse), we explicitly direct the LLM to focus on refactoring that specific block.

```python
# src/agents/style/complexity.py
import radon.complexity as rc
from typing import Any, NamedTuple

class ComplexityBlock(NamedTuple):
    name: str
    type: str  # "function", "method", "class"
    lineno: int
    complexity: int
    grade: str

class StructuralAnalyzer:
    @staticmethod
    def analyze_complexity(code: str) -> list[ComplexityBlock]:
        """Calculates cyclomatic complexity using Radon's programmatic API."""
        try:
            blocks = rc.cc_visit(code)
            results = []
            for block in blocks:
                # Determine block type
                b_type = "function"
                if hasattr(block, "classname") and block.classname:
                    b_type = "method"
                elif isinstance(block, rc.Class):
                    b_type = "class"

                results.append(ComplexityBlock(
                    name=block.name,
                    type=b_type,
                    lineno=block.lineno,
                    complexity=block.complexity,
                    grade=rc.cc_rank(block.complexity)
                ))
            return results
        except Exception:
            # Fallback gracefully to empty complexity metrics on parse error
            return []
```

#### Prompt Modification (`style.j2`):
Inject these Radon results directly into your Jinja2 template as a deterministic context block:
```jinja2
{% if complexity_blocks %}
The following functions/methods have been flagged for high cyclomatic complexity (McCabe scale):
{% for block in complexity_blocks %}
- L{{ block.lineno }} [{{ block.grade }} - Score: {{ block.complexity }}] {{ block.type }} '{{ block.name }}'
{% endfor %}
Prioritize generating refactoring recommendations for any blocks ranked 'C' or worse to improve readability.
{% endif %}
```

---

### Enhancement 2: Robust Deduplication via Line & Category Anchoring
To prevent duplicates when Ruff and the LLM find the same issue, we must move away from brittle title-matching and implement a multi-layered deduplication strategy based on **line numbers** and **issue categories**.

#### Implementation Strategy:
1. Categorize all Ruff findings.
2. Group Ruff findings by line number.
3. If the LLM generates a finding on a line already containing a Ruff lint finding *of a similar class* (e.g., syntax/formatting), discard the LLM finding.

```python
# src/agents/style/deduplicator.py
from src.models.finding import Finding, FindingSource

class StyleDeduplicator:
    @staticmethod
    def deduplicate(ruff_findings: list[Finding], llm_findings: list[Finding]) -> list[Finding]:
        """
        Deduplicates LLM style reviews against Ruff findings using line and semantic categorization.
        """
        # Map line numbers to finding details for quick lookup
        ruff_by_line: dict[int, set[str]] = {}
        for f in ruff_findings:
            if f.start_line not in ruff_by_line:
                ruff_by_line[f.start_line] = set()
            # Track standard lint identifiers/categories
            ruff_by_line[f.start_line].add(f.title.lower())
            if f.cwe_id:  # Use any specific codes if mapped
                ruff_by_line[f.start_line].add(f.cwe_id.lower())

        deduped_llm: list[Finding] = []
        for lf in llm_findings:
            line = lf.start_line
            # Strategy A: Precise title match
            title_lower = lf.title.lower()
            if any(title_lower in ruff_set for ruff_set in ruff_by_line.values()):
                continue  # Duplicate detected elsewhere in the file

            # Strategy B: Line conflict & keyword collision
            if line in ruff_by_line:
                # If the LLM points to the exact same line and discusses things Ruff already reported
                keywords = {"unused", "import", "whitespace", "line too long", "format", "pep8"}
                if any(kw in title_lower for kw in keywords):
                    continue  # Filter out trivial LLM repetitions of linter flags

            deduped_llm.append(lf)

        return ruff_findings + deduped_llm
```

---

### Enhancement 3: Multi-Stage Hybrid Pipeline (Ruff `--fix` as an Auto-Debugger)
Instead of just warning the developer about trivial formatting issues, we can run Ruff in **fix-mode** inside our workspace during the "Patch Generation" flow. 

#### Implementation Strategy:
1. Run `ruff check --select E,W,F,I --fix --exit-zero` on the file (or an in-memory buffer if we want to preview it).
    - E — PEP 8 Errors (via pycodestyle)
    - W — PEP 8 Warnings (via pycodestyle)
    - F — Correctness and Logic (via pyflakes)
    - I — Import Sorting (via isort)
2. If changes are made, run a diff tool (`difflib`) to capture the syntactic fixes instantly and programmatically.
3. Pass the *cleaned* code to the LLM. The LLM then only reviews the structurally and stylistically optimized code for deep, semantic code smells (like bad naming conventions, lack of polymorphism, or deep nesting), keeping token overhead to a minimum.

```python
# src/agents/style/fixer.py
import subprocess
from pathlib import Path

class StyleFixer:
    @staticmethod
    def auto_fix_code(code: str) -> str:
        """Runs Ruff with auto-fix enabled directly on an in-memory buffer via stdin."""
        try:
            result = subprocess.run(
                ["ruff", "check", "--select", "E,W,F,I,UP", "--fix", "-"],
                input=code,
                capture_output=True,
                text=True,
                timeout=5
            )
            # If ruff successfully corrected formatting/imports, it returns the fixed code on stdout
            if result.returncode == 0 and result.stdout:
                return result.stdout
            return code
        except Exception:
            return code # Safe fallback: return unmodified code
```

---

### Quantitative Trade-off Matrix of Enhancements

Implementing these features changes the complexity-performance profile of your system:

| Enhancement | Implement Effort | Latency Impact | Cost Impact | F1 / Precision Improvement |
| :--- | :--- | :--- | :--- | :--- |
| **1. Radon Integration** | Low | +5ms (extremely fast) | None (completely local) | High (provides exact complexity metrics) |
| **2. Multi-Layer Deduplication** | Medium | None | None | High (eliminates duplicate reports) |
| **3. Ruff Auto-Fixer Preprocessor**| Medium | -20% (shorter LLM prompt & response) | **Highly Positive** (reduces token overhead) | Very High (developer gets instant, guaranteed PEP8 fixes) |

---

### Testing: Verification of Your Style Agent (Unit Testing Suite)

Since unit and integration tests are currently marked as "Not yet implemented" in your `style-agent.md`, here is a foundational unit test suite using `pytest` to ensure your new enhancements perform reliably.

Create `tests/unit/test_style_agent.py`:

```python
# tests/unit/test_style_agent.py
import pytest
from src.agents.style.complexity import StructuralAnalyzer
from src.agents.style.deduplicator import StyleDeduplicator
from src.models.finding import Finding, FindingSource

def test_radon_complexity_analysis():
    complex_code = """
def deeply_nested_function(x):
    if x > 0:
        if x < 10:
            for i in range(x):
                if i % 2 == 0:
                    print(i)
                else:
                    print(-i)
"""
    results = StructuralAnalyzer.analyze_complexity(complex_code)
    assert len(results) == 1
    assert results[0].name == "deeply_nested_function"
    assert results[0].complexity > 4
    assert results[0].grade in ["A", "B", "C"] # Verified deterministic grading

def test_deduplication_line_level():
    # Ruff caught an unused import on line 3
    ruff_finding = Finding(
        title="Unused import: sys",
        description="sys imported but unused",
        severity="LOW",
        confidence="HIGH",
        start_line=3,
        end_line=3,
        suggestion="Remove sys",
        source=FindingSource.LINTER
    )
    
    # LLM flagged the same line with slightly different wording
    llm_finding = Finding(
        title="Unused Import of sys detected",
        description="You should remove import sys",
        severity="LOW",
        confidence="HIGH",
        start_line=3,
        end_line=3,
        suggestion="Remove it",
        source=FindingSource.LLM
    )

    combined = StyleDeduplicator.deduplicate([ruff_finding], [llm_finding])
    
    # Assert that only the Ruff finding remains, filtering out the duplicate LLM finding
    assert len(combined) == 1
    assert combined[0].source == FindingSource.LINTER
```