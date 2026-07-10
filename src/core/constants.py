"""Project-wide constants."""

from __future__ import annotations

# Commit message prefix. MUST contain GENAI=YES for enterprise pre-receive hooks
# (harmless on public GitHub). See Build_from_Scratch.md bug #4.
COMMIT_MESSAGE_PREFIX = "[pr-review] GENAI=YES"

# Stable agent identifiers.
AGENT_SECURITY = "security"
AGENT_BUG = "bug_detection"
AGENT_STYLE = "style"
AGENT_PERFORMANCE = "performance"
AGENT_FIX = "fix"

# The four analysis agents that fan out in parallel.
ANALYSIS_AGENTS = (AGENT_SECURITY, AGENT_BUG, AGENT_STYLE, AGENT_PERFORMANCE)

# Severity ordering, most severe first (used for sorting / filtering).
SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")

# Severities the FixAgent will attempt to auto-fix.
FIXABLE_SEVERITIES = ("critical", "high")

# Order in which fix categories are committed (one commit per category).
FIX_CATEGORY_ORDER = (AGENT_SECURITY, AGENT_BUG, AGENT_STYLE, AGENT_PERFORMANCE)

# Max number of files the FixAgent will touch per category (bug #9).
MAX_FIX_FILES_PER_CATEGORY = 10

# File extensions considered reviewable source (bug #11).
SOURCE_EXTENSIONS = (
    ".py",
    ".java",
    ".kt",
    ".js",
    ".ts",
    ".go",
    ".rs",
    ".xml",
    ".yml",
    ".yaml",
    ".properties",
)

# Extensions we can statically analyse with Python's `ast` module.
PYTHON_EXTENSIONS = (".py",)

# Truncate file content sent to the LLM / retriever to keep within token budgets.
MAX_CODE_CHARS_FOR_RAG = 2000
