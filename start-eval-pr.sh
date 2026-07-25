#!/bin/bash
# Start eval_PR with proper environment variable setup

cd /workspaces/multi-agent-code-review

# Load all API keys and configuration from .env
export PYTHONPATH=/workspaces/multi-agent-code-review/eval_PR:$PYTHONPATH

# Extract and export all required environment variables
export ANTHROPIC_API_KEY=$(grep "^ANTHROPIC_API_KEY=" .env | cut -d= -f2)
export DEEPSEEK_API_KEY=$(grep "^DEEPSEEK_API_KEY=" .env | cut -d= -f2)
export OPENAI_API_KEY=$(grep "^OPENAI_API_KEY=" .env | cut -d= -f2)
export GEMINI_API_KEY=$(grep "^GEMINI_API_KEY=" .env | cut -d= -f2)
export LLM_API_KEY=$(grep "^LLM_API_KEY=" .env | cut -d= -f2)
export LLM_BASE_URL=$(grep "^LLM_BASE_URL=" .env | cut -d= -f2)
export EVAL_PR_JUDGE_MODEL=$(grep "^EVAL_PR_JUDGE_MODEL=" .env | cut -d= -f2)
export EVAL_PR_BASELINE_MODEL=$(grep "^EVAL_PR_BASELINE_MODEL=" .env | cut -d= -f2)
export EVAL_PR_MAX_TOKENS=$(grep "^EVAL_PR_MAX_TOKENS=" .env | cut -d= -f2)

# Debug output
echo "================================"
echo "eval_PR Environment Setup"
echo "================================"
echo "✓ PYTHONPATH set"
echo "✓ DEEPSEEK_API_KEY: $([ -n "$DEEPSEEK_API_KEY" ] && echo 'SET' || echo 'EMPTY')"
echo "✓ ANTHROPIC_API_KEY: $([ -n "$ANTHROPIC_API_KEY" ] && echo 'SET' || echo 'EMPTY')"
echo "✓ OPENAI_API_KEY: $([ -n "$OPENAI_API_KEY" ] && echo 'SET' || echo 'EMPTY')"
echo "✓ GEMINI_API_KEY: $([ -n "$GEMINI_API_KEY" ] && echo 'SET' || echo 'EMPTY')"
echo "✓ Judge Model: $EVAL_PR_JUDGE_MODEL"
echo "✓ Baseline Model: $EVAL_PR_BASELINE_MODEL"
echo "================================"
echo ""
echo "Starting Streamlit..."
echo ""

# Start Streamlit with all env vars in the same process
streamlit run eval_PR/eval_pr/gui/app.py
