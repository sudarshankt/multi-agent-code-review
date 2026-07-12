To bridge the gap between your current implementation and your target metrics (**Vulnerability Detection F1 > 0.75**, **RAGAS Faithfulness > 0.75**, and **End-to-End Latency < 30 seconds**), we need to address four major engineering limitations in your current design:
1. **The Isolation Bottleneck:** The inability to catch vulnerabilities spanning across multiple files (e.g., a source in `views.py` reaching a sink in `db.py`).
2. **The Latency Trap:** Running costly LLM calls sequentially over every file in a PR, which will easily blow past your < 30-second limit.
3. **The Retrieval Accuracy Cap:** Simple vector semantic retrieval often misses exact matches (like specific CWE numbers) or retrieves irrelevant chunks.
4. **Parsing Fragility:** Fallback regex parsing of raw markdown blocks is prone to schema drifts.

Here is a pragmatic, production-grade architectural blueprint to enhance your Security Agent.

---

### Enhancement 1: Hybrid Static-Agentic Triage (Addressing Latency & F1)
**Concept:** Do not blindly send every file to the LLM. Instead, run a fast, local static analysis tool (like `Bandit` or `Semgrep`) as a "triage" step. Use the static tool's output to anchor and direct the LLM's attention, saving both API costs and execution time.

#### Implementation Strategy:
1. Run a local subprocess execution of Bandit (for Python) or a basic regex scanner for high-impact keywords (e.g., `execute(`, `subprocess.`, `eval(`, `os.system`).
2. Pass these structural findings to the Security Agent as "Pre-Flight Alerts."
3. If no pre-flight alerts are triggered and the file has low complexity, bypass the LLM completely for that file, drastically reducing average latency.

```python
# src/agents/security/triage.py
import subprocess
import json
from pathlib import Path
from typing import Any

class SecurityTriage:
    @staticmethod
    def run_bandit(file_path: Path) -> list[dict[str, Any]]:
        """Runs Bandit locally on a file to detect low-level security anchors."""
        try:
            result = subprocess.run(
                ["bandit", "-f", "json", str(file_path)],
                capture_output=True,
                text=True,
                check=False # Bandit returns non-zero on issues found
            )
            if not result.stdout:
                return []
            
            data = json.loads(result.stdout)
            return data.get("results", [])
        except Exception as e:
            # Fallback gracefully to empty triage list to ensure system reliability
            return []
```

#### How this changes the flow:
* Modify your `SecurityAgent.analyze` to accept the `triage_alerts: list[dict]`.
* Inject these alerts into your `security.j2` template: 
  * *“Static analysis flagged a potential SQL injection on line 42. Verify if this is a true positive or false positive using the context below.”*

---

### Enhancement 2: Graph-Based Context Stitching (Solving Multi-File Isolation)
**Concept:** While passing entire codebases to the LLM exceeds token budgets and introduces noise, analyzing files in total isolation misses cross-file data flows. We can resolve this by parsing imports using Python’s native `ast` module to resolve internal dependencies.

#### Implementation Strategy:
If `file_a.py` imports a function from `file_b.py`, we extract the signature or brief implementation of that imported function and inject it as "Dependency Context."

```python
# src/agents/security/dependency_resolver.py
import ast
from pathlib import Path

class DependencyResolver(ast.NodeVisitor):
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.dependencies: list[Path] = []

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.level and node.level > 0:
            # Relative import handling
            pass
        elif node.module:
            # Check if this maps to a local file in project root
            parts = node.module.split('.')
            possible_path = self.project_root.joinpath(*parts).with_suffix('.py')
            if possible_path.exists():
                self.dependencies.append(possible_path)
        self.generic_visit(node)

def get_file_dependencies_context(file_path: Path, project_root: Path) -> str:
    """Parses a file's AST, looks for local imports, and extracts structural code snippets."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        
        resolver = DependencyResolver(project_root)
        resolver.visit(tree)
        
        context_blocks = []
        for dep in resolver.dependencies[:3]:  # Limit to top 3 local dependencies to respect token budget
            with open(dep, "r", encoding="utf-8") as df:
                # Extract only function declarations/classes to save tokens
                dep_tree = ast.parse(df.read())
                summary = []
                for node in dep_tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        # Simple stub extraction
                        summary.append(f"def {node.name}(...): ...") 
                context_blocks.append(f"File: {dep.name}\n" + "\n".join(summary))
        
        return "\n\n".join(context_blocks)
    except Exception:
        return "" # Fail-safe: empty context
```

---

### Enhancement 3: Multi-Stage Hybrid RAG (Targeting RAGAS Metrics)
**Concept:** Simple semantic search retrieves context based on natural language similarity, which often performs poorly on technical code strings or specific CWE regulations. To achieve a **RAGAS Faithfulness > 0.75** and **Relevance > 0.70**, we should implement a **two-tier Retrieval-Reranking pipeline**.

```
┌──────────────────┐      ┌─────────────────────────┐      ┌──────────────────────┐
│  Query Code /    │ ───> │ Hybrid Search (Dense    │ ───> │ Cross-Encoder        │
│  Triage CWE IDs  │      │ Vector + BM25 Lexical)  │      │ Re-ranking (Top-5)   │
└──────────────────┘      └─────────────────────────┘      └──────────┬───────────┘
                                                                      │
                                                                      ▼
                                                           ┌──────────────────────┐
                                                           │  Filtered Context    │
                                                           │  to security.j2      │
                                                           └──────────────────────┘
```

#### Implementation Strategy:
1. **Metadata Filtering:** If your pre-flight triage (Bandit) identified a specific CWE (e.g., `CWE-89`), query ChromaDB filtering explicitly on `{"cwe_id": "CWE-89"}`.
2. **Keyword + Dense Hybrid Search:** Combine lexical matching (`BM25` on CWE ID and method names) with your dense semantic vector search (`sentence-transformers`).
3. **Cross-Encoder Re-ranking:** Query 10-15 candidates from ChromaDB, then run a lightweight, local cross-encoder model (such as `BAAI/bge-reranker-base`) via `sentence-transformers` on your backend server to select the Top-5 most relevant context passages. This dramatically increases both faithfulness and relevance.

---

### Enhancement 4: Native Structured Output via Pydantic v2 & Guardrails (Pruning Parsing Failures)
Your current system relies on string extraction (`_extract_json`) and custom coercions. In production, LLMs frequently output trailing commas, unescaped control characters, or generic markdown wrap-arounds that break parser fallbacks.

#### Implementation Strategy:
Switch to utilizing LangChain’s native `.with_structured_output()` built on top of Pydantic v2 schemas. This forces the LLM to output valid JSON conforming exactly to your field types [1].

```python
# src/agents/security/schemas.py
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class SecurityFinding(BaseModel):
    title: str = Field(description="Short, action-oriented name of the vulnerability.")
    cwe_id: str = Field(description="The matching CWE ID, e.g., 'CWE-89'.")
    severity: Severity = Field(description="Categorization of severity risk.")
    confidence: str = Field(description="Confidence score: HIGH, MEDIUM, or LOW.")
    start_line: int = Field(description="The start line where the vulnerability originates.")
    end_line: int = Field(description="The ending line of the vulnerable code block.")
    description: str = Field(description="Technical overview of the vulnerability details.")
    suggestion: str = Field(description="Actionable, safe code refactoring snippet.")
    references: list[str] = Field(description="References or grounding citations extracted from RAG.")

    @field_validator("cwe_id")
    @classmethod
    def validate_cwe(cls, v: str) -> str:
        if not v.upper().startswith("CWE-"):
            raise ValueError("CWE ID must match 'CWE-XXX' format.")
        return v.upper()

class FileSecurityReport(BaseModel):
    findings: list[SecurityFinding]
```

To call this inside your `SecurityAgent`:
```python
# In src/agents/security/agent.py
from langchain_anthropic import ChatAnthropic
from src.agents.security.schemas import FileSecurityReport

def analyze_with_structured_output(self, prompt: str) -> FileSecurityReport:
    # Initialize your model (using Claude or an OpenAI equivalent that supports tool-use / structured JSON mode)
    llm = ChatAnthropic(model_name="claude-3-5-sonnet-20240620", temperature=0)
    structured_llm = llm.with_structured_output(FileSecurityReport)
    
    # This guarantees a validated FileSecurityReport instance or raises an validation exception
    report: FileSecurityReport = structured_llm.invoke(prompt)
    return report
```

---

### Quantitative Trade-off Matrix of Enhancements

Below is a architectural trade-off analysis of these four proposed enhancements to assist your team in deciding what to implement during the upcoming integration phases:

| Enhancement | Implement Effort | Latency Impact | F1 Score Impact | Complexity | Recommended Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Hybrid Triage (Bandit)** | Low | **Highly Positive** (bypasses LLM for safe files) | Positive (drastically cuts false positives) | Low | **Must-Have** (Directly hits the <30s target) |
| **2. AST Context Stitching** | Medium | Neutral | Positive (detects cross-file vulnerabilities) | Medium | **Should-Have** (Removes isolated file blindspot) |
| **3. Hybrid RAG & Re-ranking** | Medium | Slight Negative (+100-200ms for re-ranking) | Highly Positive (targets grounding metrics) | Medium | **Should-Have** (Guarantees RAGAS metrics) |
| **4. Pydantic v2 Native Output** | Low | Neutral | Positive (stops invalid-format failures) | Low | **Must-Have** (Improves system reliability) |
