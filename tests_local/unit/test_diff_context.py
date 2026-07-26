# Purpose: Verifies that agent prompts include diff-based context so review reasoning focuses on changed lines.

from __future__ import annotations

from src.agents.security.agent import SecurityAgent
from src.models.finding import Category


class FakeLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete_json(self, prompt: str, *, system: str | None = None) -> list[dict[str, object]]:
        self.prompts.append(prompt)
        return []


async def test_security_agent_includes_diff_in_prompt() -> None:
    fake_llm = FakeLLM()
    agent = SecurityAgent(llm=fake_llm, retriever=None)  # type: ignore[arg-type]
    await agent.analyze(
        "print('hello')",
        "app.py",
        {"diffs": {"app.py": "@@ -1 +1 @@\n-print('hello')\n+print('world')"}},
    )

    prompt = fake_llm.prompts[-1]
    assert "Diff for this file:" in prompt
    assert "@@ -1 +1 @@" in prompt
    assert "Focus your analysis on the changed lines in the diff first" in prompt
