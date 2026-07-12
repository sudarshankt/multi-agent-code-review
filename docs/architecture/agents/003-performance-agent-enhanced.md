### Architectural Assessment of the Performance Agent

Current **Performance Agent** uses a highly commendable hybrid setup. By parsing the Python Abstract Syntax Tree (AST) locally and using deterministic rules (for nested loops, unbounded growth, and loop-condition calculations) before calling the LLM, you save valuable token window space and prime the LLM with concrete structural hints.

However, to hit our critical evaluation metrics—particularly keeping the **False Positive Rate (FPR) < 20%** and **Latency < 30 seconds**—the current design has three notable vulnerabilities:
1. **The "Double-Counting" Merging Flaw:** Appending static findings directly to LLM findings (`static_findings + llm_findings`) without deduplication or synthesis will result in duplicated alerts. If your static scanner identifies a nested loop and the LLM validates and explains it, the developer receives two separate reports for the exact same issue.
2. **Brittle Memory Leak Heuristics:** Your current static analyzer flags *any* `.append()` or `.add()` on local containers inside a loop. This is a major source of false positives (e.g., standard accumulator loops like `[x**2 for x in data]` or simple list building are flagged as memory leaks), which will drive your FPR well above the 20% target.
3. **Missing Critical Enterprise Bottlenecks (N+1 Queries):** While loop concatenation (`+=`) is important, database/API N+1 query patterns and synchronous blocking I/O inside async code are far more destructive to system performance in production. These are easily detectable via AST analysis.

Here is the architectural blueprint to enhance your Performance Agent.

---

### Enhancement 1: Scope-Aware AST Variable Tracking (Targeting FPR < 20%)
To prevent simple loop accumulator variables from being falsely flagged as unbounded "memory leaks," the AST memory leak analyzer must differentiate between variables whose scope is restricted to the function stack versus global/module-level variables.

#### Implementation Strategy:
Refine `memory_leaks.py` to trace where the target container was defined. Only flag container mutations (`.append()`, `.extend()`, `.add()`) inside loops if the target variable's definition scope resides *outside* the local function body (e.g., a `global` declaration, a class attribute starting with `self.`, or a module-level variable).

```python
# src/agents/performance/analyzers/memory_leaks.py
import ast
from typing import Any
from src.models.finding import Finding, FindingSource

class ScopeAwareLeakScanner(ast.NodeVisitor):
    def __init__(self):
        self.local_definitions: set[str] = set()
        self.unsafe_loop_appends: list[ast.Call] = []
        self.in_loop_depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Reset local definitions for each function to prevent cross-contamination
        self.local_definitions = {arg.arg for arg in node.args.args}
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        # Register local assignments
        if self.in_loop_depth == 0:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.local_definitions.add(target.id)
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        self.in_loop_depth += 1
        self.generic_visit(node)
        self.in_loop_depth -= 1

    def visit_While(self, node: ast.While):
        self.in_loop_depth += 1
        self.generic_visit(node)
        self.in_loop_depth -= 1

    def visit_Call(self, node: ast.Call):
        if self.in_loop_depth > 0:
            # Look for object mutations: container.append(x)
            if isinstance(node.func, ast.Attribute) and node.func.attr in ("append", "add", "extend", "insert"):
                if isinstance(node.func.value, ast.Name):
                    var_name = node.func.value.id
                    # If mutated variable is NOT defined locally within this function scope,
                    # it could be a module-level variable, global, or closure-bound container.
                    if var_name not in self.local_definitions:
                        self.unsafe_loop_appends.append(node)
                # Class attribute mutations (e.g., self.data.append(x)) are long-lived and represent potential leaks
                elif isinstance(node.func.value, ast.Attribute) and isinstance(node.func.value.value, ast.Name):
                    if node.func.value.value.id == "self":
                        self.unsafe_loop_appends.append(node)
        self.generic_visit(node)
```

---

### Enhancement 2: AST N+1 Query & Blocking Network Call Detection
In backend services, executing database queries or synchronous HTTP requests inside a loop (the classic N+1 query pattern) destroys scale. We can catch this with a highly deterministic AST node scanner.

#### Implementation Strategy:
Scan the AST for method calls matching SQL or HTTP request signatures nested inside execution loops.

```python
# src/agents/performance/analyzers/hotspots.py (Extended)
import ast
from src.models.finding import Finding, FindingSource

class NetworkLoopScanner(ast.NodeVisitor):
    def __init__(self):
        self.in_loop_depth = 0
        self.violations: list[tuple[int, str]] = []
        # Standard database/ORM query/network calls signatures
        self.blacklisted_methods = {
            "execute", "query", "filter", "get", "post", "put", 
            "delete", "fetch", "fetchall", "fetchone", "requests"
        }

    def visit_For(self, node: ast.For):
        self.in_loop_depth += 1
        self.generic_visit(node)
        self.in_loop_depth -= 1

    def visit_While(self, node: ast.While):
        self.in_loop_depth += 1
        self.generic_visit(node)
        self.in_loop_depth -= 1

    def visit_Call(self, node: ast.Call):
        if self.in_loop_depth > 0:
            method_name = None
            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                method_name = node.func.id
            
            if method_name in self.blacklisted_methods:
                self.violations.append((node.lineno, method_name))
        self.generic_visit(node)
```

---

### Enhancement 3: LLM Synthesis Layer (Solving the "Double-Counting" Flaw)
To prevent duplicate findings, do not simply append static findings to LLM findings (`static_findings + llm_findings`). Instead, implement an aggregation and consolidation step.

```
┌─────────────────────────┐
│   Static AST Findings   │ ──┐
└─────────────────────────┘   │
                              ├──> [ Synthesis / Consolidation Layer ] ──> Unique Combined Findings
┌─────────────────────────┐   │
│   Raw LLM JSON Findings  │ ──┘
└─────────────────────────┘
```

#### Implementation Strategy:
Use the LLM purely for **validation, reasoning, and synthesis**. If the static tool flags a nested loop and passes it as a prompt hint, the LLM should evaluate it. If the LLM agrees it is a real issue, it returns a enriched finding. If the LLM finds *additional* complex algorithmic issues (e.g., recursive calls with exponential space complexity), it adds them. 

The python agent merges them by treating LLM findings as **authoritative enrichments** of static findings:

```python
# src/agents/performance/agent.py (Consolidation Logic)
from src.models.finding import Finding, FindingSource

def consolidate_findings(static: list[Finding], llm_generated: list[Finding]) -> list[Finding]:
    """
    Synthesizes static AST findings with LLM analysis.
    If the LLM validated and enriched a static finding (matching line number), 
    we output only the enriched LLM version. Unvalidated static findings are retained 
    only if they represent high-confidence syntactic errors.
    """
    final_findings: list[Finding] = []
    # Index LLM findings by start line
    llm_by_line = {f.start_line: f for f in llm_generated}

    for sf in static:
        if sf.start_line in llm_by_line:
            # LLM validated the static finding. Append the enriched LLM finding (which contains explanation + patch)
            enriched = llm_by_line.pop(sf.start_line)
            # Ensure the source reflects the collaborative analysis
            enriched.source = FindingSource.HYBRID
            final_findings.append(enriched)
        else:
            # If the LLM completely ignored or rejected the static finding, we check its baseline confidence.
            # If it's a high-confidence static check (e.g. nested loop depth >= 3), keep it as a static linter report.
            if sf.confidence == "HIGH":
                final_findings.append(sf)

    # Any remaining LLM findings that weren't triggered by AST hints (purely semantic issues) are added
    final_findings.extend(llm_generated.values())
    return final_findings
```

---

### Quantitative Trade-off Matrix of Enhancements

Understanding the architectural cost-benefit analysis of these implementations:

| Enhancement | Implement Effort | Latency Impact | Cost Impact | FPR Impact (Target < 20%) |
| :--- | :--- | :--- | :--- | :--- |
| **1. Scope-Aware Variable Tracking** | Medium | Negligible | None | **Drastically Reduces FPR** (Filters out normal accumulator variables) |
| **2. N+1 AST Scanner** | Low | +2-3ms | None | **Improves Recall F1** (Anchors N+1 database/API call detection) |
| **3. LLM Synthesis Layer** | Medium | Negligible | None | **Eliminates Overlap** (Resolves redundant/double-reported findings) |

---

### Foundational Test Plan (Unit Testing)

To verify these AST rules immediately without hitting LLM API endpoints (ensuring fast dev feedback), add unit tests utilizing Python’s dynamic string parsing.

Create `tests/unit/test_performance_agent.py`:

```python
# tests/unit/test_performance_agent.py
import pytest
import ast
from src.agents.performance.analyzers.memory_leaks import ScopeAwareLeakScanner
from src.agents.performance.analyzers.hotspots import NetworkLoopScanner

def test_scope_aware_leak_scanner_safe():
    # An accumulator variable initialized inside the local function scope is safe and should NOT leak
    safe_code = """
def compile_data(raw_records):
    processed = []
    for r in raw_records:
        processed.append(r * 2)
    return processed
"""
    tree = ast.parse(safe_code)
    scanner = ScopeAwareLeakScanner()
    scanner.visit(tree)
    # Assert that standard, safe local loop appends are successfully ignored (FPR mitigation)
    assert len(scanner.unsafe_loop_appends) == 0

def test_scope_aware_leak_scanner_unsafe():
    # Appending to a module-level/global container inside a loop is unsafe
    unsafe_code = """
GLOBAL_CACHE = []

def process_batch(items):
    for item in items:
        GLOBAL_CACHE.append(item) # Unbounded global growth
"""
    tree = ast.parse(unsafe_code)
    scanner = ScopeAwareLeakScanner()
    scanner.visit(tree)
    assert len(scanner.unsafe_loop_appends) == 1

def test_n_plus_one_database_loop():
    # Database query execution nested directly inside a loop is a violation
    violating_code = """
def fetch_users_roles(users):
    results = []
    for user in users:
        role = db.query(Role).filter_by(user_id=user.id).first() # Violates N+1 query rules
        results.append((user, role))
    return results
"""
    tree = ast.parse(violating_code)
    scanner = NetworkLoopScanner()
    scanner.visit(tree)
    assert len(scanner.violations) == 1
    assert scanner.violations[0][1] == "query"
```