# Security Agent

**Path:** `src/agents/security/`

RAG-augmented LLM agent that scans source code for security vulnerabilities. Part of the fan-out/fan-in analysis pipeline in the multi-agent PR review system.

## Architecture

```
┌─────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│ SecurityRetriever│───▶│  security.j2 prompt   │───▶│   LLM (Claude /  │
│ (ChromaDB /      │    │  (Jinja2 template)    │    │   DeepSeek)      │
│  fallback)       │    └──────────────────────┘    └────────┬─────────┘
└─────────────────┘                                          │
                                                             ▼
┌─────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│  Finding objects │◀───│  findings_from_llm() │◀───│  JSON response   │
│  (list[Finding]) │    │  (parsing.py)        │    │  (extracted)     │
└─────────────────┘    └──────────────────────┘    └──────────────────┘
```

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Package marker |
| `agent.py` | `SecurityAgent` class — extends `BaseAnalysisAgent`, orchestrates RAG → prompt → LLM → parsing |
| `retriever.py` | `SecurityRetriever` class — queries ChromaDB for OWASP/CWE knowledge with hardcoded fallback |

## How it works

### 1. Entry point: `SecurityAgent.analyze(code, file_path)`

Called by `BaseAnalysisAgent.run()` for each source file in the PR diff (one file at a time, per-file isolation on failure).

### 2. RAG retrieval: `SecurityRetriever.retrieve(code)`

- Truncates `code` to `MAX_CODE_CHARS_FOR_RAG` (2000 chars) to stay within embedding token budgets
- Queries ChromaDB's `owasp_knowledge` collection for the top-5 most semantically relevant OWASP/CWE documents
- **If ChromaDB is unavailable** (import error, connection failure, or empty result): falls back to 8 hardcoded CWE knowledge entries covering SQLi, command injection, XSS, path traversal, hardcoded secrets, weak crypto, insecure deserialization, and SSRF
- Returns formatted bullet-point string (`- CWE-XXX: ...`)

### 3. Prompt rendering: `security.j2`

Jinja2 template at `src/prompts/templates/security.j2`:

- Sets role: "senior application security engineer"
- **SCOPE**: injection, XSS, deserialization, hardcoded secrets, weak crypto, auth/authz, SSRF, path traversal, OWASP Top 10, CWE
- Explicitly excludes: logic errors, performance, style/naming, general code quality
- Injects RAG context (if available) before the code
- Includes `_common.j2` — JSON output contract requiring a flat array of objects with `title`, `description`, `severity`, `confidence`, `start_line`, `end_line`, `suggestion`, `cwe_id`, `references`

### 4. LLM call: `LLMService.complete_json(prompt)`

- Sends the rendered prompt to the LLM (Claude via ChatAnthropic, or DeepSeek via custom base URL)
- Temperature=0 for deterministic output
- `_extract_json()` robustly parses the response: tries markdown-fenced blocks first, then raw text, then balanced `{...}`/`[...]` substrings
- Falls back to `[]` on parse failure

### 5. Parsing: `findings_from_llm(payload, Category.SECURITY, file_path)`

In `src/agents/parsing.py`:

- Accepts list payloads or `{"findings": [...]}` / `{"issues": [...]}` wrapped dicts
- Coerces severity aliases (`moderate` → `MEDIUM`, `informational` → `INFO`), defaults missing to `MEDIUM`
- Coerces confidence (`high`/`medium`/`low`), defaults missing to `MEDIUM`
- Falls back on title (`title` → `name` → `issue` → from description) and description (`description` → `detail` → `message` → from title)
- Skips items with no title and no description
- Truncates titles to 200 characters
- Maps `line` → `start_line`, `fix` → `suggestion`, `cwe` → `cwe_id`
- Sets `source = FindingSource.LLM`

### 6. Error isolation

`BaseAnalysisAgent.run()` wraps each file's `analyze()` call in a `try/except` — one file's LLM failure (network error, model 404, etc.) does not halt analysis of other files. Failures are logged as `agent_file_failed` with the error message.

## Dependencies

| Dependency | Used for | Optional? |
|---|---|---|
| `src.services.llm_service.LLMService` | LLM completion via langchain-anthropic | No |
| `src.infrastructure.chromadb.client` | Semantic RAG retrieval | Yes — graceful fallback |
| `src.prompts.loader` | Jinja2 prompt template rendering | No |
| `src.agents.parsing` | JSON → Finding object conversion | No |
| `src.agents.base.BaseAnalysisAgent` | Per-file iteration, extension filter, error isolation | No |

## Configuration

| Env var | Config path | Default | Purpose |
|---|---|---|---|
| `LLM_API_KEY` | `settings.llm.api_key` | `None` | Anthropic/DeepSeek API key |
| `LLM_BASE_URL` | `settings.llm.base_url` | `None` | Custom LLM endpoint (gateway/proxy) |
| `PRIMARY_MODEL` | `settings.llm.primary_model` | `"deepseek-v4-pro"` | Model to use for analysis |
| `LLM_MAX_TOKENS` | `settings.llm.max_tokens` | `4096` | Max response tokens |
| `CHROMADB_MODE` | `settings.chromadb.mode` | `"embedded"` | `"embedded"` or `"http"` |

## Testing

| Layer | Location | Tests | Requires API key? |
|---|---|---|---|
| **Unit** | `tests/unit/test_security_retriever.py` | 8 tests — ChromaDB fallback/available, top_k, formatting, truncation | No |
| **Unit** | `tests/unit/test_security_parsing.py` | 22 tests — severity/confidence coercion, title/desc fallbacks, CWE mapping, edge cases | No |
| **Unit** | `tests/unit/test_security_agent.py` | 16 tests — full pipeline with `FakeLLMService`, golden-file fixtures, `run()` aggregation | No |
| **Integration** | `tests/integration/test_security_agent.py` | 5 tests — real LLM call against known-vulnerable code, ChromaDB degradation, clean-code negative test | Yes |

### Running tests

```bash
# Unit tests (fast, no API key needed):
uv run pytest tests/unit/test_security_retriever.py tests/unit/test_security_parsing.py tests/unit/test_security_agent.py -v

# Integration tests (requires LLM_API_KEY):
uv run pytest tests/integration/test_security_agent.py -v -s
```

## Known limitations

- **LLM 404 with non-Anthropic models**: `LLMService._build_model()` always uses `ChatAnthropic`. If using a custom model like `deepseek-v4-pro`, you must set `LLM_BASE_URL` to a compatible proxy/gateway endpoint, or update `_build_model()` to route based on `model_provider`.
- **No context sharing across files**: Each file is analyzed in isolation — if a vulnerability spans two files (e.g., a tainted source in file A reaching a sink in file B), the agent won't catch it.
- **ChromaDB requires separate setup**: Run `uv run python scripts/ingest_owasp.py` to populate the knowledge base, or the agent uses hardcoded fallback knowledge.
