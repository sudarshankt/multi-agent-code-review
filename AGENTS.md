# AGENTS.md

## Purpose
This repository implements an AI-powered multi-agent code review and auto-debugging system. Any agent working in this codebase should follow the architecture, safety, and verification expectations below when designing or implementing changes.

## Project Context
The system reviews pull requests by orchestrating specialized agents for:
- security analysis
- bug detection
- style and performance review
- patch generation
- test generation

The implementation is built around LangGraph orchestration, FastAPI APIs, structured Pydantic models, and optional RAG over OWASP/CWE knowledge.

## Core Design Principles
1. Keep agents specialized and decoupled.
   - The orchestrator owns routing, shared state, and workflow control.
   - Avoid making agents depend on each other directly.

2. Use deterministic tools first, then LLM reasoning.
   - Prefer static analysis, AST parsing, metrics, and rule-based checks before invoking LLMs.
   - Use LLMs for higher-level reasoning, structured output, and contextual explanation.

3. Favor explicit, minimal state.
   - Keep shared state small and typed.
   - Avoid storing large unnecessary payloads in graph state.

4. Prefer structured outputs.
   - Use Pydantic models for request/response schemas, agent results, and LLM structured responses.
   - Keep outputs consistent and machine-parseable.

5. Design for safety and reliability.
   - Do not execute untrusted code without sandboxing or safe execution controls.
   - Prefer read-only or isolated operations for analysis and test execution.

## Repository Map
- src/agents/orchestrator/ — LangGraph state, routing, and workflow graph
- src/agents/security/ — security analysis and retrieval logic
- src/agents/bug_detection/ — AST and bug analysis logic
- src/agents/style/ — style and performance checks
- src/agents/fix/ — patch generation and remediation logic
- src/services/ — GitHub, Git, and LLM integration helpers
- src/models/ — domain models and schemas
- src/api/ — FastAPI routes, schemas, and middleware
- src/core/ — configuration, logging, and shared exceptions
- src/prompts/ — prompt templates and loaders
- tests/ — unit and integration tests
- dashboard/ — React/Vite frontend for review progress and findings

## Implementation Expectations
- Follow the existing package structure instead of introducing unrelated abstractions.
- Reuse existing base classes and service patterns before creating new ones.
- Keep code typed and readable. Use Python 3.12+ features carefully and consistently.
- Use async patterns where the project already uses them, especially in API and orchestration flows.
- Keep external integrations behind service-layer abstractions.
- Use environment-based configuration for secrets and runtime settings.

## Coding Standards
- Write clear, maintainable Python code with docstrings where useful.
- Prefer small, focused functions and explicit error handling.
- Do not hardcode secrets, tokens, or URLs.
- Keep prompts and templates in the prompt system rather than embedding raw prompt text in business logic.
- Preserve the existing logging conventions and avoid introducing noisy or inconsistent logs.
- If working on SSE or dashboard features, keep event payloads consistent with existing API behavior.

## Testing Expectations
- Add or update tests for every behavior change.
- Prefer unit tests for logic and integration tests for workflow/API behavior.
- Use pytest and existing fixtures where possible.
- If a change affects a prompt, agent, or workflow, verify both happy-path and failure-path behavior.

## Verification Before Completion
Do not consider a task complete until relevant verification has been run.
- Run targeted pytest tests for the modified area.
- Run ruff checks when Python files are changed.
- If the change affects the API or orchestration flow, validate the behavior with the most relevant test or smoke check.

## Project-Specific Guardrails
- Avoid introducing unnecessary dependencies.
- Keep latency and cost in mind; do not make redundant model calls when deterministic checks are enough.
- Preserve the existing GitHub-first workflow and avoid introducing local clone-based behavior unless explicitly requested.
- Keep patch generation constrained, reviewable, and safe.
- If adding new agent behavior, ensure it fits the orchestrator state model and can be tested independently.

## Documentation Expectations
When making significant changes, update the relevant documentation in:
- README.md
- docs/HLD.md
- docs/LLD.md
- docs/USER_FLOWS.md

## Working Style
1. Inspect the relevant module and surrounding tests before changing behavior.
2. Implement the smallest change that solves the problem.
3. Verify the change with tests and linting.
4. Summarize what changed, why it changed, and how it was verified.
