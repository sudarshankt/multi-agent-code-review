# Findings Architecture & Deduplication

## Overview

Each finding has a **source** and **category** to ensure clarity about how it was generated and where it belongs.

## Finding Sources

All findings come from **Claude LLM** (not hardcoded rules):

| Source | Agent | How It Works |
|--------|-------|-------------|
| **LLM** | SecurityAgent | Claude analyzes code for OWASP/CWE vulnerabilities with RAG context |
| **LLM** | BugDetectionAgent | Claude finds logic errors, null checks, exceptions (AST is used for hints only) |
| **LLM** | StyleAgent | Claude identifies readability issues (Ruff is used for filtering only) |
| **LLM** | PerformanceAgent | Claude detects inefficient algorithms, N+1, leaks (AST is used for hints only) |

> **Note**: AST analyzers and Ruff are used as *hints* to the LLM, not as direct findings. The LLM then generates the actual findings with context and detailed explanations.

## Finding Categories

Each finding has a strict category with clear boundaries:

### 🔒 Security
**Scope**: OWASP Top 10 + CWE vulnerabilities
- SQL/Command/LDAP Injection
- Cross-Site Scripting (XSS)
- Insecure Deserialization
- Hardcoded Secrets/Credentials
- Weak Cryptography
- Authentication/Authorization Flaws
- Server-Side Request Forgery (SSRF)
- Path Traversal
- Similar vulnerability patterns

**NOT**: Logic errors, performance issues, style problems

### 🐛 Bug Detection
**Scope**: Functional correctness issues
- Logic Errors
- Off-by-one errors
- Null/None pointer dereferences
- Unhandled exceptions
- Incorrect error handling
- Race conditions
- Wrong API usage
- Edge cases causing runtime failures

**NOT**: Security vulnerabilities, performance inefficiencies, style issues

### 🎨 Style
**Scope**: Readability and maintainability
- Unclear variable/function naming
- Dead code
- Overly complex functions
- Missing docstrings
- Inconsistent code style
- Anti-patterns
- Issues NOT caught by Ruff linter

**NOT**: Security issues, functional bugs, performance problems

### ⚡ Performance
**Scope**: Runtime efficiency and resource usage
- Inefficient algorithms (O(n²) when O(n) possible)
- N+1 query patterns
- Repeated work in loops
- Unbounded memory growth/leaks
- Blocking I/O in async code
- Obvious hotspots

**NOT**: Security vulnerabilities, logic bugs, style issues

## Deduplication Process

After all 4 agents complete analysis in parallel, findings are deduplicated:

### 1. Similarity Detection
Findings are compared by:
- **Title similarity** (string matching, 70%+ threshold)
- **File path + line number** (exact match)
- **Description keyword overlap** (85%+ similarity)

### 2. Duplicate Handling
When similar findings are detected:
1. Keep the **highest severity** version
2. Reassign to the **most appropriate category** based on keyword analysis
3. Log the deduplication event

### 3. Example

```
Before deduplication:
✅ Security: "SQL Injection Vulnerability in query()" (HIGH)
✅ Bug: "SQL query is vulnerable to injection" (MEDIUM)
✅ Performance: "Unparameterized SQL might be slow" (LOW)

After deduplication:
✅ Security: "SQL Injection Vulnerability in query()" (HIGH) ← Kept (highest severity)
❌ Bug: Removed (duplicate)
❌ Performance: Removed (duplicate)
```

## How to Verify Findings Are LLM-Generated

Check the finding object in the API response:

```json
{
  "id": "abc123",
  "title": "SQL Injection Vulnerability",
  "description": "User input is concatenated directly into SQL query without parameterization...",
  "category": "security",
  "severity": "high",
  "confidence": "high",
  "source": "llm",  // ← This indicates Claude generated it
  "agent_name": "security",
  "start_line": 42,
  "suggestion": "Use parameterized queries with placeholders...",
  "cwe_id": "CWE-89",
  "references": ["https://owasp.org/www-community/attacks/SQL_Injection"]
}
```

**Source values**:
- `"llm"` = Claude LLM generated
- `"ast_analyzer"` = Python AST static analysis (rare)
- `"linter"` = Ruff or similar linter (rare)

## Prompt Engineering Details

Each agent's prompt includes:

1. **Clear scope statement** - What issues to find
2. **Explicit exclusions** - What NOT to find
3. **Hints from static tools** - For context, not as findings
4. **JSON output contract** - Structured response format
5. **RAG context** (Security only) - OWASP/CWE knowledge base

### Example: Security Agent Prompt

```
You are a senior application security engineer reviewing a code change.

SCOPE: Identify ONLY security vulnerabilities: injection, XSS, insecure
deserialization, hardcoded secrets, weak crypto, auth flaws, SSRF, path
traversal, and similar OWASP Top 10 + CWE issues.

DO NOT REPORT: Logic errors, performance issues, style/naming issues, or
general code quality problems (those are handled by other reviewers).

[RAG context with OWASP knowledge...]

File: example.py
```
[code...]
```

Respond with ONLY a JSON array...
```

## Viewing Deduplication in Logs

When running `make run-all`, check backend logs for:

```
[info] findings_deduplicated original_count=15 deduplicated_count=12 removed_count=3
[debug] finding_deduplicated title="SQL Injection Vulnerability" duplicates_removed=2 assigned_agent=security
```

## No More Overlaps

With these changes:
- ✅ Each finding appears in **exactly one category**
- ✅ All findings are **LLM-generated** (with optional AST/linter hints)
- ✅ **Highest severity** duplicate is kept
- ✅ **Clear source tracking** (source field in JSON)
- ✅ **Deduplication logged** for transparency

---

**Questions?** Check the logs during analysis to see which findings were deduplicated and why.
