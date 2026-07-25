#!/usr/bin/env python3
"""Check API key status in Streamlit app context."""

import sys
from pathlib import Path

# Simulate Streamlit app's loading order
print("=" * 70)
print("CHECKING STREAMLIT API KEY LOADING")
print("=" * 70)

# Step 1: Load .env like app.py does
print("\n[STEP 1] Loading .env file (like app.py does)...")
from dotenv import load_dotenv
workspace_root = Path(__file__).resolve().parent
env_file = workspace_root / ".env"
print(f"  .env path: {env_file}")
print(f"  .env exists: {env_file.exists()}")
if env_file.exists():
    load_dotenv(env_file)
    print("  ✓ load_dotenv() called")
else:
    print("  ✗ .env not found!")
    load_dotenv()  # Fallback

# Step 2: Check environment
print("\n[STEP 2] Checking environment after load_dotenv()...")
import os
print(f"  OPENAI_API_KEY: {bool(os.environ.get('OPENAI_API_KEY'))}")
print(f"  DEEPSEEK_API_KEY: {bool(os.environ.get('DEEPSEEK_API_KEY'))}")
print(f"  ANTHROPIC_API_KEY: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")

# Step 3: Import config (this happens AFTER load_dotenv in app.py)
print("\n[STEP 3] Importing eval_pr.config (after load_dotenv)...")
eval_pr_root = workspace_root / "eval_PR"
sys.path.insert(0, str(eval_pr_root))
sys.path.insert(0, str(workspace_root))
from eval_pr.config import (
    OPENAI_API_KEY,
    DEEPSEEK_API_KEY,
    ANTHROPIC_API_KEY,
    JUDGE_MODEL,
    BASELINE_MODEL,
)

print(f"  OPENAI_API_KEY from config: {bool(OPENAI_API_KEY)} (len={len(OPENAI_API_KEY) if OPENAI_API_KEY else 0})")
print(f"  DEEPSEEK_API_KEY from config: {bool(DEEPSEEK_API_KEY)} (len={len(DEEPSEEK_API_KEY) if DEEPSEEK_API_KEY else 0})")
print(f"  ANTHROPIC_API_KEY from config: {bool(ANTHROPIC_API_KEY)} (len={len(ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else 0})")

# Step 4: Test client creation
print("\n[STEP 4] Testing client creation...")
from eval_pr.config import get_client_for_model, get_provider_for_model

models_to_test = [
    ("deepseek-v4-pro", "deepseek"),
    ("gpt-4o", "openai"),
    ("claude-opus-4-8", "anthropic"),
]

for model, expected_provider in models_to_test:
    provider = get_provider_for_model(model)
    print(f"\n  Model: {model}")
    print(f"    Provider detected: {provider}")
    
    # Try with environment keys
    api_keys = {
        "deepseek": DEEPSEEK_API_KEY,
        "openai": OPENAI_API_KEY,
        "anthropic": ANTHROPIC_API_KEY,
    }
    
    client = get_client_for_model(model, api_keys=api_keys)
    print(f"    Client created: {type(client).__name__ if client else 'NONE'}")
    
    if not client:
        print(f"    ✗ FAILED - Check that {provider.upper()}_API_KEY is set")
    else:
        print(f"    ✓ OK - Client ready")

# Step 5: Report current models
print("\n[STEP 5] Current model configuration...")
print(f"  JUDGE_MODEL: {JUDGE_MODEL}")
print(f"  BASELINE_MODEL: {BASELINE_MODEL}")

print("\n" + "=" * 70)
print("API KEY CHECK COMPLETE")
print("=" * 70)
