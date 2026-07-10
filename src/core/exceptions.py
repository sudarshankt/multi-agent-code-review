"""Exception hierarchy with per-exception retry policy metadata.

Each exception carries a `retry_policy` describing how callers should retry:
- backoff: "exponential" | "linear" | "none" | "immediate"
- max_attempts: total attempts including the first

See Build_from_Scratch.md section 5 (exceptions) for the matrix.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    backoff: str  # "exponential" | "linear" | "none" | "immediate"
    max_attempts: int

    @property
    def retryable(self) -> bool:
        return self.backoff != "none" and self.max_attempts > 1


class PRReviewError(Exception):
    """Base error for all PR-review failures."""

    retry_policy = RetryPolicy(backoff="none", max_attempts=1)

    def __init__(self, message: str, *, detail: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


# ---- GitHub ----
class GitHubAPIError(PRReviewError):
    retry_policy = RetryPolicy(backoff="exponential", max_attempts=3)


class GitHubRateLimitError(GitHubAPIError):
    retry_policy = RetryPolicy(backoff="linear", max_attempts=5)


# ---- LLM ----
class LLMError(PRReviewError):
    retry_policy = RetryPolicy(backoff="exponential", max_attempts=3)


class LLMRateLimitError(LLMError):
    retry_policy = RetryPolicy(backoff="linear", max_attempts=5)


class LLMContextLengthError(LLMError):
    retry_policy = RetryPolicy(backoff="none", max_attempts=1)


# ---- Agents ----
class AgentError(PRReviewError):
    retry_policy = RetryPolicy(backoff="exponential", max_attempts=2)


class AgentTimeoutError(AgentError):
    retry_policy = RetryPolicy(backoff="immediate", max_attempts=1)


# ---- RAG ----
class RAGError(PRReviewError):
    retry_policy = RetryPolicy(backoff="exponential", max_attempts=2)


# ---- Git operations ----
class GitOperationError(PRReviewError):
    retry_policy = RetryPolicy(backoff="immediate", max_attempts=2)


# ---- Webhook ----
class WebhookValidationError(PRReviewError):
    retry_policy = RetryPolicy(backoff="none", max_attempts=1)


# ---- Queue ----
class QueueError(PRReviewError):
    retry_policy = RetryPolicy(backoff="exponential", max_attempts=3)
