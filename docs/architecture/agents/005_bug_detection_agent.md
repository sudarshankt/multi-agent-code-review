# Multi-Agent Code Review & Auto-Debugging System Architecture

## 1. Overall System Architecture
The system utilizes a **LangGraph Multi-Agent Pipeline** to orchestrate specialized agents for automated code review, vulnerability assessment, and patch generation.

### 1.1 Input Sources
*   **GitHub Webhook**: Automatically triggers on pull requests or code pushes.
*   **User Browser**: Web-based interface for interactive manual submission.
*   **CI/CD Trigger**: Programmatic invocation from continuous integration pipelines.
*   **FastAPI Application Middleware & API**: Handles data routing and authenticates requests between input interfaces and the core agent pipeline.

### 1.2 Core LangGraph Multi-Agent Pipeline
The architecture employs a centralized orchestration mechanism grounded in a structured environment context:
1.  **Supervisor Agent**: Acts as the central orchestrator routing tasks to specialized agents based on code characteristics and pre-processing alerts.
2.  **Three Specialist Agents**:
    *   **Security Agent**: Evaluates security risks, referencing the RAG Pipeline.
    *   **Bug Detection Agent**: Investigates functional correctness, runtime exceptions, and logical defects.
    *   **Style & Performance Agent**: Checks coding standards, formatting guidelines, and optimization vectors.
3.  **RAG Pipeline**: Augments the Security Agent with domain-specific knowledge bases:
    *   *OWASP Top-10 Knowledge Base* & *CWE References*
    *   *BGE Embeddings* storing vector representations in a *ChromaDB Vector DB*
    *   *Cross-Encoder Re-Ranking* for highly accurate contextual context retrieval.
4.  **Aggregate Findings**: Merges issues discovered across all three specialist agents.
5.  **Patch & Test Generation**:
    *   **Patch Generator Agent**: Proposes automated fixes for identified bugs and security issues.
    *   **Test Generator Agent**: Generates test assertions to validate proposed patches.

---

## 2. AI-Enabled Code Analysis Architecture (Bug Detection Focus)
The Bug Detection Agent specializes in analyzing incoming pull request source code diffs to find syntax failures, structural bugs, and dynamic logic bugs.

### 2.1 Bug Detection Workflow
![Agent Architecture ](005_bug_detection_arch.png)
1.  **Input Interface (PR Source Code Diff)**: Captures modified lines, deletions (`-`), additions (`+`), and contextual lines.
2.  **Knowledge Integrator**: Combines raw Pull Request data with structured semantic insights derived from AST tools.
3.  **AST Tools (Static Code Analysis)**: Transforms flat source code into a structured, hierarchical object to programmatically scan structural components.
4.  **LLM Core Execution**: Receives the structured context, raw code diffs, and integrated syntax knowledge to evaluate dynamic logic flows.
5.  **Output Interface (Agent Analysis Report)**: Produces a structured report detailing discovered flaws.

### 2.2 Sample Structured Analysis Output
*   **Finding 1**:
    *   **ID**: FIND_001 | **Category**: Security | **Severity**: `CRITICAL` | **Confidence**: HIGH
    *   **Title**: Function Name Mismatch
    *   **Description**: Call to 'sneak' with typo as 'sreak'.
    *   **Location**: `example_script.py`, Lines 8-10
    *   **Source**: `AST_TOOL`
*   **Finding 2**:
    *   **ID**: FIND_002 | **Category**: Performance | **Severity**: `Major: Logic Error in Loop`
    *   **Description**: Line 18 error in loop construction.
    *   **Location**: `example_script.py`, Lines 8-10
    *   **Source**: `AST_TOOL`
*   **Finding 3**:
    *   **ID**: FIND_003 | **Category**: Style | **Severity**: `MINOR`
    *   **Title**: Dead Code
    *   **Location**: `example_script.py`, Lines 8-10
    *   **Source**: `AST_TOOL`
*   **Report Metadata**:
    *   **Timestamp**: 2024-05-15 10:30 UTC
    *   **Analysis Config**: `full_scan`
    *   **Report Format**: Structured JSON/HTML

---

## 3. Abstract Syntax Tree (AST) & Static Code Analysis Capabilities

### 3.1 Core AST Functionalities
By transforming flat text files into hierarchical token patterns, developers can deterministically inspect code without standard text processing inaccuracies:
1.  **Precise Static Code Analysis**: Scans syntax structures, semantic usage, and recurring anti-patterns.
2.  **Automated Refactoring**: Identifies outdated patterns or deprecated language syntax for seamless automated upgrading.
3.  **Safe Evaluation of Untrusted Inputs**: Utilizes `ast.literal_eval()` to safely process strings containing Python literals (lists, dicts, tuples) avoiding severe security risks associated with arbitrary `eval()`.
4.  **Programmatic Introspection**: Traverses code trees systematically to trace specific structures, metadata properties, or object definitions.
5.  **Dependency Tracking**: Parses import declarations and explicit function scopes to build cross-module dependency graphs.

 The native `ast` library provides powerful programmatic tools to read, navigate, and change code on the fly:

| Method / Utility | Functional Description |
| :--- | :--- |
| `ast.parse(source)` | Converts a string of raw Python code into an AST object tree structure. |
| `ast.unparse(tree)` | Reverses the process, converting an AST object tree back into clean, formatted Python source code strings. |
| `ast.literal_eval(node_or_string)` | Safely evaluates strings containing basic Python literals (strings, numbers, tuples, lists, dicts) without executing arbitrary code, offering a secure alternative to dangerous `eval()` calls. |
| `ast.NodeVisitor` | A base class that can be subclassed to walk systematically through the tree structure to scan for explicit code patterns (e.g., finding all function definitions). |
| `ast.NodeTransformer` | A native processing class that allows you to automatically rewrite or modify specific nodes, altering how the code behaves before it compiles. |

### 3.2 Exhaustive Code Error Categories Detected via AST & Static Analysis

#### A. Syntax Failures
An AST parse failure occurs when a code parser or linter encounters a formatting, physical, or structural error that violates the formal grammar rules of the language, preventing translation into a tree.
*   **Syntax Violations**: Tokens ordered in invalid mathematical or logical configurations.
*   **Indentation Issues**: Misaligned whitespace blocks breaking Python's block structure rules.
*   **Version Mismatches**: Code parsing utilizing features native to newer language runtimes than specified.
*   **Corrupted or Malformed Data**: Raw file reading drops or corrupted block endings.
*   **Stack Depth Limits**: Nesting statements or expressions beyond the compiler's parsing threshold.

#### B. Semantic Errors
*   **Variables, Scope, and Resolution Issues**:
    *   *Undefined Variables (NameError patterns)*: Referencing a variable name that has not been bound in the local, global, or built-in scope.
    *   *Variable Shadowing*: Re-declaring a local variable or function parameter with the exact same name as an outer scope variable or a built-in function (e.g., naming a variable `list` or `str`).
    *   *Unused Local Variables / Imports*: Allocating memory or importing modules that are never referenced anywhere down the tree branch.
    *   *Global/Nonlocal Statement Placement*: Declaring `global x` or `nonlocal x` after `x` has already been assigned or used locally within that block.
    *   *Late Binding in Closures*: Capturing loop variables inside a lambda or nested function, causing all iterations to incorrectly resolve to the final loop iteration value.
*   **Control Flow and Execution Anomalies**:
    *   *Dead Code*: Entire blocks of statements hidden under conditional structures that statically resolve to false (e.g., `if False:`, `if __debug__ == False:`).
    *   *Infinite Loops*: Loops whose test nodes evaluate to a constant truth value (e.g., `while True:`) missing a matching internal `Break` node.
    *   *Break / Continue Misplacement*: Finding a `break` or `continue` node outside the ancestral subtree of a parent `For` or `While` loop loop.
    *   *Return Outside Function*: Finding a `Return` or `Yield` node inside code that is not wrapped inside a proper `FunctionDef` node.
    *   *Unreachable Post-Return Code*: Statements written directly after a `return`, `raise`, or `break` statement within the exact same structural block.
*   **Function and Object Call Deficiencies**:
    *   *Mutable Default Arguments*: Passing a List `[]` or Dict `{}` node as a default argument value in a `FunctionDef`, which persists across multiple function calls.
    *   *Argument Signature Mismatches*: Calling a function with the wrong number of positional arguments, duplicate keyword arguments, or missing mandatory keyword-only arguments.
    *   *Unresolved Attributes (AttributeError patterns)*: Calling a method or accessing a property on an object where the static type definition lacks that explicit attribute.
    *   *Abstract Class Instantiation*: Attempting to instantiate a class node that inherits from `abc.ABC` without overriding all of its abstract methods.
    *   *Incorrect super() Usage*: Calling `super()` inside a function node that is not a method of a class node.

#### C. Security Vulnerabilities and Anti-Patterns
*   **Dynamic Code Execution**: Usage of `Call` nodes pointing to `eval()`, `exec()`, or `compile()` with non-literal string arguments.
*   **Hardcoded Secrets**: Plain-text assignment nodes (`Constant`) containing cryptographic keys, API tokens, or passwords mapped to sensitive identifier names.
*   **Insecure Deserialization**: Calling vulnerable parser formats like `pickle.loads()`, `marshal`, or unsafe YAML loaders.
*   **Shell Injection Vectors**: Utilizing `subprocess.Popen` or `os.system` with `shell=True` passed alongside variable string formatting.
*   **Insecure Cryptography / Hashing**: Utilizing broken hashing algorithms like `hashlib.md5()` or `hashlib.sha1()` for security verification contexts.

#### D. Exception Handling Anti-Patterns
*   **Bare Except Clauses**: Utilizing `except:` instead of `except Exception:` or specific error types, which catches unintended system signals like `KeyboardInterrupt`.
*   **Overly Broad Exceptions**: Catching base-level errors (like `except BaseException:`) across massive blocks of multi-layered code.
*   **Shadowing Exception Names**: Assigning an exception instance to a variable name that wipes out an existing variable in that scope (e.g., `except Exception as e:`).
*   **Raising Non-Exception Objects**: Passing constants, raw strings, or uninstantiated non-exception classes to a `Raise` node.
*   **Lost Exceptions in Finally**: Placing a `return` or `break` node inside a `finally` block, which silently swallows raised exceptions from the `try` block.

#### E. Type and Operator Inconsistencies
*   **Impossible Type Comparisons**: Evaluating a conditional expression between completely incompatible data types (e.g., checking if an integer is identical to a list: `5 == []`).
*   **Invalid Operator Operations**: Combining binary operators with incompatible types, such as adding a string to an integer node (`"string" + 1`).
*   **Duplicate Dictionary Keys**: Defining a `Dict` literal node containing identical hashable keys, causing silent data overwrites at execution time.
*   **Subscripting Non-Indexable Objects**: Attempting to use a `Subscript` node on a variable determined to be a primitive integer, float, or boolean.

---


## 4. Prompt Engineering & Grounded Execution
The Bug Detection Agent operates under strict systemic bounds to prevent overlap with the Security or Style/Performance agents.

### Bug Detection System Prompt Blueprint
```jinja2
You are a meticulous software engineer hunting for correctness bugs in a code change.

**SCOPE**: Look for logic errors, off-by-one, null/None dereferences, unhandled exceptions, incorrect error handling, race conditions, wrong API usage, and edge cases that cause runtime failures.

**DO NOT REPORT**: Security vulnerabilities (injection, XSS, secrets, crypto), performance issues (slow algorithms, memory leaks), or style issues. Also skip items already flagged by the static analyzer below.

Focus on functional correctness and runtime safety.

{% if static_findings %}
A static analyzer already flagged these (use as hints, do not repeat):
{% for item in static_findings %}
- L{{ item.start_line }}: {{ item.title }}
{% endfor %}
{% endif %}

File: {{ file_path }}
```
```python
{{ code }}
```
```jinja2
{% include "_common.j2" %}
```

---

## 5. Evaluation & Roadmap Trackers

### 5.1 Benchmark Dataset Overview (`BugsInPy`)
*   **Description**: A comprehensive database hosting real-world bugs in Python programs to enable controlled testing and developer debugging studies.
*   **Volume**: Contains ~500 real bugs extracted from 17 production-grade, open-source Python programs.
*   **Usage**: Utilized to measure regression performance, agent precision, and system recovery metrics.
*   **RAG Knowledge Base Note**: Evaluation of utilizing `BugsInPy` directly as a semantic RAG retriever yielded **inefficient results**. It does not perform effectively for matching logical pull request discrepancies to historical database bug-fixes due to contextual variation.

### 5.2 Next steps

| Evaluation / Task |  Next Steps |
| :--- |  :--- |
| **Benchmark Dataset Integration** |  Finalize evaluation metrics across all 500 bugs. |
| **LLM as a Judge Evaluation Framework** | Establish rigid alignment templates for structural verification. |
| **Agent Implementation** |  Refine state management and message loops inside LangGraph. |
| **AST Check Enhancements** |  Incorporate all possible structural validation utilities from native Python AST. |
| **RAG: Bug Dataset Evaluation** |  Pivot from direct matching towards localized code pattern indexing. |
| **Integration in Overall System** | Execute systematic load testing, baseline validations, and latency optimization. |
