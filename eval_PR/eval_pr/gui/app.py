"""eval_PR GUI — Streamlit app with dynamic model and API key configuration.

A guided interface for auditing one real PR: explains what the tool does,
accepts the PR and fixed output as either uploaded files or pasted text,
allows selecting different LLM providers and models for judging and baseline,
runs the real audit logic (not a mock), and renders the verdict and full
report with plain-language explanations.

Run with:
    pip install -r requirements.txt
    streamlit run eval_pr/gui/app.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Load environment variables BEFORE importing config
from dotenv import load_dotenv

# Find and load the .env file from workspace root
workspace_root = Path(__file__).resolve().parents[3]  # Go up to workspace root
env_file = workspace_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()  # Fallback to default search

import streamlit as st

logger = logging.getLogger(__name__)

EVAL_PR_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(EVAL_PR_ROOT))

from eval_pr.config import (  # noqa: E402
    AVAILABLE_MODELS,
    AUDIT_MODELS,
    BASELINE_MODEL,
    JUDGE_MODEL,
    ANTHROPIC_API_KEY,
    DEEPSEEK_API_KEY,
    OPENAI_API_KEY,
    api_key_configured,
    get_provider_for_model,
)
from eval_pr.judge import ATTACK_CATEGORIES, CATEGORIES  # noqa: E402
from eval_pr.run_single_pr import audit, render_markdown  # noqa: E402

st.set_page_config(page_title="eval_PR — Single PR Audit", page_icon="🔍", layout="wide")

# Initialize session state with environment variables only
# NOTE: judge_model and baseline_model are managed by their selectbox widgets (via key parameter)
if "result" not in st.session_state:
    st.session_state.result = None
if "pr_label" not in st.session_state:
    st.session_state.pr_label = "PR"
if "max_tokens" not in st.session_state:
    from eval_pr.config import MAX_TOKENS as _DEFAULT_MAX_TOKENS
    st.session_state.max_tokens = _DEFAULT_MAX_TOKENS
if "pr_text" not in st.session_state:
    st.session_state.pr_text = ""
if "fixed_output_text" not in st.session_state:
    st.session_state.fixed_output_text = ""

# Set up initial values that selectbox will use via index parameter
_initial_judge_model = JUDGE_MODEL
_initial_baseline_model = BASELINE_MODEL

# API keys are always loaded from environment (not modifiable in UI)
ENV_API_KEYS = {
    "anthropic": ANTHROPIC_API_KEY,
    "deepseek": DEEPSEEK_API_KEY,
    "openai": OPENAI_API_KEY,
}

# Log which API keys are configured for debugging
_configured_keys = [k for k, v in ENV_API_KEYS.items() if v]
logger.info(f"Initialized Streamlit app with API keys configured for: {_configured_keys}")
if not _configured_keys:
    logger.warning("No API keys configured! Check that .env file exists and is loaded before this module.")
else:
    logger.info(f"API key details: anthropic={bool(ANTHROPIC_API_KEY)}, deepseek={bool(DEEPSEEK_API_KEY)}, openai={bool(OPENAI_API_KEY)}")



# ============================================================================
# GitHub Link Fetching Functions
# ============================================================================

def fetch_pr_diff(pr_link: str) -> tuple[str, str]:
    """Fetch PR diff using gh CLI, targeting the repo parsed from the PR URL
    (not the cwd's default repo) so this works for any owner/repo."""
    import subprocess
    try:
        if "/pull/" not in pr_link:
            return None, "Invalid PR URL — expected .../owner/repo/pull/123"
        repo_part, pr_number = pr_link.split("/pull/")
        pr_number = pr_number.split("?")[0].split("/")[0].strip()
        parts = repo_part.replace("https://github.com/", "").replace("http://github.com/", "").strip("/").split("/")
        if len(parts) < 2:
            return None, "Invalid PR URL — could not determine owner/repo"
        owner, repo = parts[0], parts[1]
        result = subprocess.run(
            ["gh", "pr", "diff", pr_number, "-R", f"{owner}/{repo}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout, f"PR #{pr_number} ({owner}/{repo})"
        else:
            return None, f"Failed to fetch PR: {result.stderr[:200]}"
    except Exception as e:
        return None, f"Error: {str(e)[:200]}"


def fetch_branch_code(repo_url: str, branch: str, file_path: str = "") -> tuple[str, str]:
    """Fetch code from a branch using GitHub API (requires GITHUB_TOKEN)."""
    import subprocess
    import json
    try:
        # Extract owner/repo from URL
        parts = repo_url.replace("https://github.com/", "").replace(".git", "").split("/")
        if len(parts) < 2:
            return None, "Invalid GitHub URL"
        
        owner, repo = parts[0], parts[1]
        
        # Use gh API to get branch contents
        if file_path:
            result = subprocess.run(
                ["gh", "api", f"repos/{owner}/{repo}/contents/{file_path}?ref={branch}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        else:
            # Get all Python files in repo at branch
            result = subprocess.run(
                ["gh", "repo", "view", f"{owner}/{repo}", "--json", "name"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                # Fetch tree structure
                result = subprocess.run(
                    ["gh", "api", f"repos/{owner}/{repo}/git/trees/{branch}?recursive=1"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if isinstance(data, dict) and "content" in data:
                # Single file
                import base64
                content = base64.b64decode(data["content"]).decode("utf-8")
                return content, f"Branch: {branch}/{file_path or 'root'}"
            elif isinstance(data, dict) and "tree" in data:
                # Multiple files - concatenate Python files
                files_content = []
                for item in data["tree"]:
                    if item.get("type") == "blob" and item.get("path", "").endswith(".py"):
                        files_content.append(f"\n\n{'='*60}\n# File: {item['path']}\n{'='*60}\n")
                        # Get file content
                        file_result = subprocess.run(
                            ["gh", "api", f"repos/{owner}/{repo}/contents/{item['path']}?ref={branch}"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if file_result.returncode == 0:
                            file_data = json.loads(file_result.stdout)
                            if "content" in file_data:
                                import base64
                                files_content.append(base64.b64decode(file_data["content"]).decode("utf-8"))
                return "".join(files_content), f"Branch: {branch} (all .py files)"
            else:
                return None, f"Unexpected response format"
        else:
            return None, f"Failed to fetch branch: {result.stderr[:200]}"
    except Exception as e:
        return None, f"Error: {str(e)[:200]}"


def fetch_commit_code(commit_url: str) -> tuple[str, str]:
    """Fetch code from a commit."""
    import subprocess
    try:
        parts = commit_url.replace("https://github.com/", "").split("/")
        if len(parts) < 5:
            return None, "Invalid commit URL"
        
        owner, repo, _, commit = parts[0], parts[1], parts[2], parts[4]
        
        # Use gh API to get commit
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/commits/{commit}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            # Get the diff
            result = subprocess.run(
                ["gh", "api", f"repos/{owner}/{repo}/commits/{commit}", "--jq", ".patch"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout, f"Commit: {commit[:7]}"
        
        return None, f"Failed to fetch commit: {result.stderr[:200]}"
    except Exception as e:
        return None, f"Error: {str(e)[:200]}"


@st.cache_data(ttl=300)  # Cache for 5 minutes
def test_api_key(provider: str, api_key: str) -> bool:
    """Test if an API key works by making a minimal API call."""
    if not api_key:
        return False
    
    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            client.messages.create(
                model="claude-sonnet-5",
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
                timeout=10.0,
            )
            return True
        elif provider == "deepseek":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, base_url="https://api.deepseek.com/anthropic")
            client.messages.create(
                model="deepseek-v4-pro",
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
                timeout=10.0,
            )
            return True
        elif provider == "openai":
            import openai
            client = openai.OpenAI(api_key=api_key, timeout=10.0)
            client.chat.completions.create(
                model="gpt-3.5-turbo",
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}],
            )
            return True
    except Exception:
        return False
    
    return False


# ============================================================================
# Build model list first (used in sidebar)
# ============================================================================

_all_models = []
for provider, models in AUDIT_MODELS.items():
    for model in models:
        _all_models.append((model, provider))

_model_values = [model for model, _ in _all_models]

# ============================================================================
# Sidebar Configuration
# ============================================================================

with st.sidebar:
    st.header("⚙️ Configuration")
    
    # API Key Status (read-only from environment)
    st.subheader("🔑 API Keys Status")
    st.caption("Keys loaded from `.env` file only.")
    
    providers = ["anthropic", "deepseek", "openai"]
    provider_names = {
        "anthropic": "Anthropic (Claude)",
        "deepseek": "DeepSeek",
        "openai": "OpenAI (GPT)",
    }
    
    for provider in providers:
        display_name = provider_names[provider]
        key_value = ENV_API_KEYS.get(provider, "")
        
        # Test if key works
        if key_value:
            is_working = test_api_key(provider, key_value)
            status_icon = "✅" if is_working else "❌"
        else:
            status_icon = "❌"
        
        st.markdown(f"{status_icon} **{display_name}**")
    
    st.divider()
    
    # Model Selection
    st.subheader("🤖 Model Selection")
    
    # Judge model selection
    try:
        judge_idx = _model_values.index(_initial_judge_model)
    except (ValueError, IndexError):
        judge_idx = 0
    
    # Selectbox is controlled entirely by its key - Streamlit manages session state
    st.selectbox(
        "Judge Model",
        _model_values,
        index=judge_idx,
        key="judge_model",
        format_func=lambda x: f"{x} ({get_provider_for_model(x)})"
    )
    
    # Baseline model selection
    try:
        baseline_idx = _model_values.index(_initial_baseline_model)
    except (ValueError, IndexError):
        baseline_idx = min(1, len(_model_values) - 1)
    
    st.selectbox(
        "Baseline Model",
        _model_values,
        index=baseline_idx,
        key="baseline_model",
        format_func=lambda x: f"{x} ({get_provider_for_model(x)})"
    )
    
    # Max tokens
    max_tokens = st.slider(
        "Max Tokens",
        1000,
        32000,
        st.session_state.max_tokens,
        step=1000,
        help="Reasoning models (e.g. deepseek-v4-pro) spend part of this budget on internal 'thinking' before the JSON answer. Too low and the response comes back empty.",
    )
    st.session_state.max_tokens = max_tokens
    
    st.divider()
    
    # Status display
    st.subheader("📊 Status")
    
    # Check which API keys are configured
    keys_configured = {provider: bool(key) for provider, key in ENV_API_KEYS.items()}
    judge_provider = next(p for m, p in _all_models if m == st.session_state.judge_model)
    baseline_provider = next(p for m, p in _all_models if m == st.session_state.baseline_model)
    
    judge_status = "✅" if keys_configured.get(judge_provider) else "❌"
    baseline_status = "✅" if keys_configured.get(baseline_provider) else "❌"
    
    st.markdown(f"**Judge:** {judge_status} {st.session_state.judge_model}")
    st.markdown(f"**Baseline:** {baseline_status} {st.session_state.baseline_model}")
    
    api_status = sum(1 for v in keys_configured.values() if v)
    st.caption(f"{api_status}/{len(providers)} API keys configured")
    
    if not any(keys_configured.values()):
        st.warning("⚠️ No API keys in .env — results will be placeholders")


# ============================================================================
# Header
# ============================================================================

st.title("🔍 eval_PR — Single Real-PR Audit")
st.markdown(
    "Audit **one specific pull request** your multi-agent code-review system has "
    "already fully processed. You provide the original PR and the system's actual "
    "fixed output; an independent judge checks whether every issue was really found "
    "and fixed, whether the review held up against manipulation attempts, and how it "
    "compares to a simple single-prompt baseline — then gives you a clear **GO / NO-GO**."
)

with st.expander("📖 How this works", expanded=False):
    st.markdown(
        """
**Inputs — both must already exist, this tool does not run your pipeline:**
1. **The original PR** — the code as submitted.
2. **The fixed output** — what your system actually produced for it: the Security,
   Bug, Style, and Performance agents' findings, the generated patch, and test results.

**What the judge checks, in one independent audit:**
- **Per category** (Security / Bug / Style / Performance): what issues really exist,
  what got patched, what still remains — determined independently, not by trusting
  the agents' own claims.
- **Quality rubric (1–5):** coverage, noise, actionability, coherence, overall — scored
  for your system *and* for a zero-shot baseline (one plain LLM call, no agents), so
  you can see what the multi-agent approach actually adds.
- **Adversarial resistance:** checked against 4 known manipulation patterns
  (instruction override, role confusion, fake verdict injection, output suppression),
  plus a separate check that the final patched code itself carries no adversarial content.

**The verdict is computed by fixed rules, not left to the model's opinion:**
NO-GO if any category still has a remaining issue, any detected attack wasn't resisted,
the fixed output itself is still adversarial, or the patch scores 1/5 on actionability
(broken/non-functional). GO otherwise.
        """
    )

st.divider()


# ============================================================================
# Input
# ============================================================================

st.header("1. Provide the PR and its fixed output")

input_mode = st.radio(
    "Input method",
    ["Upload files", "Paste text", "GitHub PR/Branch/Commit link", "Mixed (link + file)", "Before/After Code (PR vs Branch/Commit)"],
    horizontal=False,
)

# Use session state to persist values across rerenders
if not hasattr(st.session_state, 'pr_text'):
    st.session_state.pr_text = ""
if not hasattr(st.session_state, 'fixed_output_text'):
    st.session_state.fixed_output_text = ""
if not hasattr(st.session_state, 'pr_label'):
    st.session_state.pr_label = "PR"

pr_text = st.session_state.pr_text
fixed_output_text = st.session_state.fixed_output_text
pr_label = st.session_state.pr_label

if input_mode == "Upload files":
    st.subheader("📁 Upload Files")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Original PR**")
        pr_file = st.file_uploader(
            "Choose PR file",
            type=None,
            help="Any text file (.py, .diff, .txt, .md, .json) containing the PR code or diff",
            key="pr_file_uploader",
        )
        if pr_file:
            st.session_state.pr_text = pr_file.read().decode("utf-8", errors="replace")
            st.session_state.pr_label = pr_file.name
    with col2:
        st.write("**Fixed Output**")
        fixed_output_file = st.file_uploader(
            "Choose fixed output file",
            type=None,
            help="Text or JSON file with your system's findings, patch, and test results",
            key="fixed_file_uploader",
        )
        if fixed_output_file:
            st.session_state.fixed_output_text = fixed_output_file.read().decode("utf-8", errors="replace")

elif input_mode == "Paste text":
    st.subheader("📝 Paste Text")
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.pr_text = st.text_area(
            "Original PR",
            value=st.session_state.pr_text,
            height=300,
            placeholder="Paste the PR diff, code, or code snippet here...",
            key="pr_textarea",
        )
    with col2:
        st.session_state.fixed_output_text = st.text_area(
            "Fixed output",
            value=st.session_state.fixed_output_text,
            height=300,
            placeholder="Paste the system's findings + patch + test results here...",
            key="fixed_textarea",
        )

elif input_mode == "GitHub PR/Branch/Commit link":
    st.subheader("🔗 GitHub PR / Branch / Commit Link")
    col1, col2 = st.columns(2)
    with col1:
        link_type = st.radio(
            "Link type",
            ["PR", "Branch", "Commit"],
            key="github_link_type",
        )
        
        if link_type == "PR":
            pr_link = st.text_input(
                "GitHub PR URL",
                placeholder="https://github.com/owner/repo/pull/123",
                help="e.g., https://github.com/Agentic-Code-Reviewers/multi-agent-code-review/pull/14",
                key="pr_link_input",
            )
            if pr_link and st.button("📥 Fetch PR from GitHub", key="fetch_pr_btn"):
                code, label = fetch_pr_diff(pr_link)
                if code:
                    st.session_state.pr_text = code
                    st.session_state.pr_label = label
                    st.success(f"✅ {label}")
                else:
                    st.error(label)
        
        elif link_type == "Branch":
            branch_url = st.text_input(
                "GitHub Branch URL or Repo URL",
                placeholder="https://github.com/owner/repo or https://github.com/owner/repo/tree/branch-name",
                help="Full repo URL or branch URL",
                key="branch_link_input",
            )
            branch_name = st.text_input(
                "Branch name (if not in URL)",
                placeholder="main, develop, test/code-issues-demo",
                key="branch_name_input",
            )
            file_path = st.text_input(
                "Specific file (optional, leave empty for all .py files)",
                placeholder="src/main.py",
                key="branch_file_input",
            )
            
            if branch_url and st.button("📥 Fetch Branch Code from GitHub", key="fetch_branch_btn"):
                # Extract branch from URL if provided
                if "/tree/" in branch_url:
                    branch = branch_url.split("/tree/")[-1].split("?")[0]
                    repo_url = "/".join(branch_url.split("/tree/")[0:1])
                else:
                    repo_url = branch_url
                    branch = branch_name or "main"
                
                if not branch:
                    st.error("Branch name required")
                else:
                    code, label = fetch_branch_code(repo_url, branch, file_path)
                    if code:
                        st.session_state.pr_text = code
                        st.session_state.pr_label = label
                        st.success(f"✅ {label}")
                    else:
                        st.error(label)
        
        elif link_type == "Commit":
            commit_url = st.text_input(
                "GitHub Commit URL",
                placeholder="https://github.com/owner/repo/commit/abc123def",
                help="e.g., https://github.com/Agentic-Code-Reviewers/multi-agent-code-review/commit/abc123",
                key="commit_link_input",
            )
            if commit_url and st.button("📥 Fetch Commit from GitHub", key="fetch_commit_btn"):
                code, label = fetch_commit_code(commit_url)
                if code:
                    st.session_state.pr_text = code
                    st.session_state.pr_label = label
                    st.success(f"✅ {label}")
                else:
                    st.error(label)
    
    with col2:
        st.write("**Fixed Output**")
        fixed_output_type = st.radio(
            "Fixed output source",
            ["Paste text", "Upload file"],
            key="fixed_output_source",
        )
        if fixed_output_type == "Paste text":
            st.session_state.fixed_output_text = st.text_area(
                "Fixed output (paste)",
                value=st.session_state.fixed_output_text,
                height=250,
                placeholder="Paste findings + patch + test results...",
                key="fixed_textarea_link_mode",
            )
        else:
            fixed_output_file = st.file_uploader(
                "Choose fixed output file",
                type=None,
                help="Text or JSON file",
                key="fixed_file_uploader_link_mode",
            )
            if fixed_output_file:
                st.session_state.fixed_output_text = fixed_output_file.read().decode("utf-8", errors="replace")

elif input_mode == "Mixed (link + file)":
    st.subheader("🔗 GitHub Link (PR/Branch/Commit) + 📁 Fixed Output File")
    col1, col2 = st.columns(2)
    with col1:
        mixed_link_type = st.radio(
            "Link type",
            ["PR", "Branch", "Commit"],
            key="mixed_link_type",
        )
        
        if mixed_link_type == "PR":
            pr_link = st.text_input(
                "GitHub PR URL",
                placeholder="https://github.com/owner/repo/pull/123",
                key="pr_link_mixed",
            )
            if pr_link and st.button("📥 Fetch PR from GitHub", key="fetch_pr_mixed"):
                code, label = fetch_pr_diff(pr_link)
                if code:
                    st.session_state.pr_text = code
                    st.session_state.pr_label = label
                    st.success(f"✅ {label}")
                else:
                    st.error(label)
        
        elif mixed_link_type == "Branch":
            branch_url = st.text_input(
                "GitHub Branch URL or Repo URL",
                placeholder="https://github.com/owner/repo or https://github.com/owner/repo/tree/branch-name",
                key="branch_link_mixed",
            )
            branch_name = st.text_input(
                "Branch name (if not in URL)",
                placeholder="main, develop, test/code-issues-demo",
                key="branch_name_mixed",
            )
            
            if branch_url and st.button("📥 Fetch Branch Code", key="fetch_branch_mixed"):
                # Extract branch from URL if provided
                if "/tree/" in branch_url:
                    branch = branch_url.split("/tree/")[-1].split("?")[0]
                    repo_url = "/".join(branch_url.split("/tree/")[0:1])
                else:
                    repo_url = branch_url
                    branch = branch_name or "main"
                
                if not branch:
                    st.error("Branch name required")
                else:
                    code, label = fetch_branch_code(repo_url, branch)
                    if code:
                        st.session_state.pr_text = code
                        st.session_state.pr_label = label
                        st.success(f"✅ {label}")
                    else:
                        st.error(label)
        
        elif mixed_link_type == "Commit":
            commit_url = st.text_input(
                "GitHub Commit URL",
                placeholder="https://github.com/owner/repo/commit/abc123def",
                key="commit_link_mixed",
            )
            if commit_url and st.button("📥 Fetch Commit", key="fetch_commit_mixed"):
                code, label = fetch_commit_code(commit_url)
                if code:
                    st.session_state.pr_text = code
                    st.session_state.pr_label = label
                    st.success(f"✅ {label}")
                else:
                    st.error(label)
    
    with col2:
        st.write("**Fixed Output File**")
        fixed_output_file = st.file_uploader(
            "Choose fixed output file",
            type=None,
            help="Text or JSON with findings, patch, test results",
            key="fixed_file_mixed",
        )
        if fixed_output_file:
            st.session_state.fixed_output_text = fixed_output_file.read().decode("utf-8", errors="replace")

elif input_mode == "Before/After Code (PR vs Branch/Commit)":
    st.subheader("📊 Before/After Code Comparison")
    st.write("Fetch original PR code and fixed code from GitHub, with optional findings file")
    
    col1, col2, col3 = st.columns(3)
    
    # Column 1: Original Code (PR)
    with col1:
        st.write("**1️⃣ Original Code (PR)**")
        original_link_type = st.radio(
            "Original source",
            ["PR", "Branch", "Commit"],
            key="before_after_original_type",
        )
        
        if original_link_type == "PR":
            pr_link = st.text_input(
                "PR URL",
                placeholder="https://github.com/owner/repo/pull/123",
                key="before_after_pr_link",
            )
            if pr_link and st.button("📥 Fetch Original PR", key="before_after_fetch_pr"):
                code, label = fetch_pr_diff(pr_link)
                if code:
                    st.session_state.pr_text = code
                    st.session_state.pr_label = label
                    st.success(f"✅ {label}")
                else:
                    st.error(label)
        
        elif original_link_type == "Branch":
            branch_url = st.text_input(
                "Repo URL or Branch URL",
                placeholder="https://github.com/owner/repo",
                key="before_after_original_branch_url",
            )
            branch_name = st.text_input(
                "Branch name",
                placeholder="main",
                key="before_after_original_branch",
            )
            
            if branch_url and st.button("📥 Fetch Original Branch", key="before_after_fetch_original_branch"):
                if "/tree/" in branch_url:
                    branch = branch_url.split("/tree/")[-1].split("?")[0]
                    repo_url = "/".join(branch_url.split("/tree/")[0:1])
                else:
                    repo_url = branch_url
                    branch = branch_name or "main"
                
                if not branch:
                    st.error("Branch name required")
                else:
                    code, label = fetch_branch_code(repo_url, branch)
                    if code:
                        st.session_state.pr_text = code
                        st.session_state.pr_label = f"Branch: {branch}"
                        st.success(f"✅ {label}")
                    else:
                        st.error(label)
        
        elif original_link_type == "Commit":
            commit_url = st.text_input(
                "Commit URL",
                placeholder="https://github.com/owner/repo/commit/abc123",
                key="before_after_original_commit",
            )
            if commit_url and st.button("📥 Fetch Original Commit", key="before_after_fetch_original_commit"):
                code, label = fetch_commit_code(commit_url)
                if code:
                    st.session_state.pr_text = code
                    st.session_state.pr_label = label
                    st.success(f"✅ {label}")
                else:
                    st.error(label)
    
    # Column 2: Fixed Code (PR/Branch/Commit)
    with col2:
        st.write("**2️⃣ Fixed Code (PR/Branch/Commit)**")
        fixed_link_type = st.radio(
            "Fixed source",
            ["PR", "Branch", "Commit"],
            key="before_after_fixed_type",
        )
        
        if fixed_link_type == "PR":
            fixed_pr_link = st.text_input(
                "PR URL",
                placeholder="https://github.com/owner/repo/pull/123",
                key="before_after_fixed_pr_link",
            )
            if fixed_pr_link and st.button("📥 Fetch Fixed PR", key="before_after_fetch_fixed_pr"):
                code, label = fetch_pr_diff(fixed_pr_link)
                if code:
                    st.session_state.fixed_output_text = code
                    st.success(f"✅ {label}")
                else:
                    st.error(label)
        
        elif fixed_link_type == "Branch":
            fixed_branch_url = st.text_input(
                "Repo URL or Branch URL",
                placeholder="https://github.com/owner/repo",
                key="before_after_fixed_branch_url",
            )
            fixed_branch_name = st.text_input(
                "Branch name",
                placeholder="fix/code-issues",
                key="before_after_fixed_branch",
            )
            
            if fixed_branch_url and st.button("📥 Fetch Fixed Branch", key="before_after_fetch_fixed_branch"):
                if "/tree/" in fixed_branch_url:
                    branch = fixed_branch_url.split("/tree/")[-1].split("?")[0]
                    repo_url = "/".join(fixed_branch_url.split("/tree/")[0:1])
                else:
                    repo_url = fixed_branch_url
                    branch = fixed_branch_name or "main"
                
                if not branch:
                    st.error("Branch name required")
                else:
                    code, label = fetch_branch_code(repo_url, branch)
                    if code:
                        st.session_state.fixed_output_text = code
                        st.success(f"✅ {label}")
                    else:
                        st.error(label)
        
        elif fixed_link_type == "Commit":
            fixed_commit_url = st.text_input(
                "Commit URL",
                placeholder="https://github.com/owner/repo/commit/def456",
                key="before_after_fixed_commit",
            )
            if fixed_commit_url and st.button("📥 Fetch Fixed Commit", key="before_after_fetch_fixed_commit"):
                code, label = fetch_commit_code(fixed_commit_url)
                if code:
                    st.session_state.fixed_output_text = code
                    st.success(f"✅ {label}")
                else:
                    st.error(label)
    
    # Column 3: Optional Findings
    with col3:
        st.write("**3️⃣ Optional Findings**")
        findings_input = st.radio(
            "Findings source (optional)",
            ["None", "Paste JSON", "Upload file"],
            key="before_after_findings_type",
        )
        
        findings_text = ""
        if findings_input == "Paste JSON":
            findings_text = st.text_area(
                "Paste findings JSON",
                height=200,
                placeholder="Paste audit findings/issues JSON...",
                key="before_after_findings_paste",
            )
        elif findings_input == "Upload file":
            findings_file = st.file_uploader(
                "Upload findings file",
                type=None,
                help="Text or JSON with audit findings",
                key="before_after_findings_upload",
            )
            if findings_file:
                findings_text = findings_file.read().decode("utf-8", errors="replace")
        
        if findings_text:
            st.session_state.fixed_output_text = findings_text if not st.session_state.fixed_output_text else f"{st.session_state.fixed_output_text}\n\n---\nAdditional Findings:\n{findings_text}"

run_clicked = st.button("▶️ Run Audit", type="primary", use_container_width=True)

st.divider()


# ============================================================================
# Run
# ============================================================================

if run_clicked:
    # Use session state for validation
    pr_text = st.session_state.get("pr_text", "").strip()
    fixed_output_text = st.session_state.get("fixed_output_text", "").strip()
    
    if not pr_text or not fixed_output_text:
        st.error("Both the PR and the fixed output are required.")
    else:
        with st.spinner("Auditing... this calls the judge model and the zero-shot baseline model."):
            try:
                # EXPLICIT DEBUG - print everything
                logger.info(f"=" * 80)
                logger.info(f"AUDIT START - Detailed Debug:")
                logger.info(f"  JUDGE_MODEL (env): {JUDGE_MODEL}")
                logger.info(f"  BASELINE_MODEL (env): {BASELINE_MODEL}")
                logger.info(f"  st.session_state.judge_model: {st.session_state.judge_model}")
                logger.info(f"  st.session_state.baseline_model: {st.session_state.baseline_model}")
                logger.info(f"  type(st.session_state.judge_model): {type(st.session_state.judge_model)}")
                logger.info(f"  type(st.session_state.baseline_model): {type(st.session_state.baseline_model)}")
                
                # Check if they match env
                judge_match = st.session_state.judge_model == JUDGE_MODEL
                baseline_match = st.session_state.baseline_model == BASELINE_MODEL
                logger.info(f"  Judge matches env? {judge_match}")
                logger.info(f"  Baseline matches env? {baseline_match}")
                logger.info(f"=" * 80)
                
                result = audit(
                    pr_text,
                    fixed_output_text,
                    judge_model=st.session_state.judge_model,
                    baseline_model=st.session_state.baseline_model,
                    api_keys=ENV_API_KEYS,
                    max_tokens=st.session_state.max_tokens,
                )
                st.session_state.result = result
                st.session_state.pr_label = pr_label
            except Exception as e:
                st.error(f"Audit failed: {e}")
                st.session_state.result = None


# ============================================================================
# Results
# ============================================================================

result = st.session_state.result
if result is None:
    st.info("Provide a PR and fixed output above, then click **Run Audit** to see results here.")
else:
    m = result["metrics"]

    st.header("2. Results")

    if result.get("is_placeholder"):
        st.warning(
            "⚠️ **Placeholder result** — no real model call succeeded (no API key, or the "
            "call failed). This demonstrates the tool's output shape, not a real audit."
        )

    # --- Verdict banner ---
    if m["verdict"] == "GO":
        st.success("## ✅ GO")
    else:
        st.error("## ❌ NO-GO")
        st.markdown("**Reasons:**")
        for r in m["verdict_reasons"]:
            st.markdown(f"- {r}")

    st.caption(
        "The verdict is computed by fixed rules from the findings below — the model never "
        "declares it itself."
    )

    # --- Categorical findings ---
    st.subheader("Categorical findings")
    cat_cols = st.columns(4)
    status_icon = {"resolved": "✅", "unresolved": "❌", "none_found": "⚪"}
    for col, cat in zip(cat_cols, CATEGORIES):
        c = m[cat]
        status = m["category_status"][cat]
        with col:
            st.markdown(f"**{cat.capitalize()}** {status_icon[status]}")
            st.caption(status)
            with st.expander("Details"):
                st.markdown(f"**Identified:** {', '.join(c['identified']) or '(none)'}")
                st.markdown(f"**Patched:** {', '.join(c['patched']) or '(none)'}")
                st.markdown(f"**Remaining:** {', '.join(c['remaining']) or '(none)'}")

    st.divider()

    # --- Rubric comparison ---
    st.subheader("Quality rubric — this system vs. a zero-shot baseline")
    
    with st.expander("📋 What each dimension means", expanded=False):
        st.markdown("""
**Coverage** — Do the findings catch the actual issues in the PR?
- **5:** All real issues found; nothing material missed.
- **1:** Most real issues missed; findings are sparse or irrelevant.

**Noise** — Are the reported findings real, or are they false alarms?
- **5:** No false positives; every issue reported is genuine.
- **1:** Mostly noise; false alarms far outnumber real findings.

**Actionability** — Are the reported findings clear and actionable for the developer?
- **5:** Each issue is specific, has a clear root cause, and comes with a concrete fix.
- **1:** Findings are vague, contradictory, or provide no guidance on how to fix them.

**Coherence** — Do the findings make sense together? Are they logically consistent?
- **5:** Findings are well-organized, non-contradictory, and clearly relate to each other.
- **1:** Findings are scattered, confusing, or logically inconsistent.

**Overall** — Holistic judgment: if I had to pick one score for "how good is this review?", what would it be?
- **5:** This review is excellent: thorough, clear, and trustworthy.
- **1:** This review is barely useful; I would not trust it.
        """)
    
    rubric, baseline, delta = m["rubric"], m["baseline_rubric"], m.get("rubric_delta_vs_baseline")
    rubric_rows = []
    for dim in ("coverage", "noise", "actionability", "coherence", "overall"):
        rubric_rows.append({
            "Dimension": dim.capitalize(),
            "System": rubric.get(dim, "—"),
            "Baseline": baseline.get(dim, "—"),
            "Delta": delta[dim] if delta else "—",
        })
    st.table(rubric_rows)
    if not delta:
        st.caption("Delta not shown — one or both rubric scores are still placeholders.")
    st.caption(
        "The baseline never affects the verdict — it's shown only as evidence of what the "
        "multi-agent architecture adds over a single plain LLM call on this PR."
    )

    st.divider()

    # --- Adversarial resistance ---
    st.subheader("Adversarial resistance (4 attack categories)")
    rate = m["resistance_rate"]
    if rate is None:
        st.info("No attack pattern detected in this PR — resistance rate not applicable.")
    elif rate < 1.0:
        st.error(f"Resistance rate: {rate} — at least one detected attack was not resisted.")
    else:
        st.success(f"Resistance rate: {rate} — all detected attacks were resisted.")

    adv_rows = []
    for attack in ATTACK_CATEGORIES:
        a = m["adversarial"][attack]
        adv_rows.append({
            "Attack category": attack.replace("_", " "),
            "Detected": a["detected"],
            "Resisted": a["resisted"],
            "Rationale": a["rationale"],
        })
    st.table(adv_rows)

    if m["fixed_output_contains_adversarial_content"]:
        st.error(f"🚨 Fixed output itself still contains adversarial content — {m['fixed_output_adversarial_rationale']}")
    else:
        st.success("✅ Fixed output itself is clean of adversarial content.")

    st.divider()

    # --- Summary ---
    st.subheader("Judge's summary")
    st.write(m.get("summary_rationale") or "(not provided)")

    st.divider()

    # --- Publish / download ---
    st.subheader("📤 Publish results")
    md_report = render_markdown(result, pr_label=st.session_state.pr_label)
    import json as _json

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 Download as Markdown",
            md_report,
            file_name=f"eval_PR_report_{st.session_state.pr_label}.md",
            mime="text/markdown",
        )
    with col2:
        st.download_button(
            "📥 Download as JSON",
            _json.dumps(result, indent=2),
            file_name=f"eval_PR_result_{st.session_state.pr_label}.json",
            mime="application/json",
        )
