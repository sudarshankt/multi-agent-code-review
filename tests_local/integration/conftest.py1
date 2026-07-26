"""Integration test configuration."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

# Load .env so os.environ picks up LLM_API_KEY for the skip guard below.
load_dotenv()


@pytest.fixture(autouse=True)
def require_llm_api_key() -> None:
    """Skip all integration tests if LLM_API_KEY is not set."""
    if not os.environ.get("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY not set — required for integration tests")