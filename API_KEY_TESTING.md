# Quick API Key Testing Reference

This is a quick guide to test all LLMs and GitHub integration with their API keys.

## Quick Start

### Test Everything (Recommended)
```bash
./init-setup.sh
```
This runs comprehensive tests including:
- Phase 10: LLM API key and connectivity tests  
- Phase 11: GitHub API and token tests

### Test LLM Only
```bash
source .venv/bin/activate
python scripts/test-llm-keys.py
```

### Test GitHub Only
```bash
source .venv/bin/activate
python scripts/test-github-token.py
```

## What Gets Tested

### LLM Testing (test-llm-keys.py)
✓ API key is configured  
✓ API key format is valid  
✓ Provider connectivity (DeepSeek/Anthropic)  
✓ LLM service wrapper works  
✓ Basic completions work  
✓ System prompts work  
✓ JSON extraction works  
✓ Fallback model is available  

### GitHub Testing (test-github-token.py)
✓ GitHub API URL is configured  
✓ GitHub token is set (optional)  
✓ GitHub service initializes  
✓ API connectivity works  
✓ Authentication is ready  

## Expected Output

### Successful LLM Test
```
✓ PASS - Environment Validation
✓ PASS - LLM Connectivity
✓ PASS - Fallback Model
✓ PASS - Model Parameters

Passed: 4/4
✓ ALL LLM TESTS PASSED
```

### Successful GitHub Test
```
✓ PASS - Environment Configuration
✓ PASS - GitHub Service
✓ PASS - API Connectivity

Passed: 3/3
✓ GITHUB VERIFICATION COMPLETE
```

## Common Issues

### "LLM_API_KEY is not set"
```bash
# Check if key is set
echo $LLM_API_KEY

# Add to .env if missing
echo "LLM_API_KEY=sk-your-key-here" >> .env

# Re-test
python scripts/test-llm-keys.py
```

### "API test failed: 401 Unauthorized"
- Your API key is invalid or expired
- Get a new key from your provider
- Update `.env` with correct key

### "Connection timeout"
- Check internet: `ping api.deepseek.com`
- Check firewall settings
- Try again - may be network hiccup

### GitHub tests show "Endpoint not found (404)"
- This is normal - just means API is reachable
- Tests still pass

## Environment Variables

### For LLM Testing
```bash
LLM_API_KEY=sk-your-api-key              # Required
PRIMARY_MODEL=deepseek-v4-pro             # Optional
FALLBACK_MODEL=deepseek-v4-pro            # Optional
LLM_BASE_URL=https://api.deepseek.com/anthropic  # Optional
MODEL_PROVIDER=deepseek                   # Optional
```

### For GitHub Testing
```bash
GITHUB_TOKEN=ghp_your-token-here          # Optional
GITHUB_API_BASE_URL=https://api.github.com # Optional
```

## Integration with Initialization

The comprehensive init-setup.sh now includes:

**Phase 10**: Comprehensive LLM API key testing
- Checks configuration
- Tests connectivity
- Verifies service works

**Phase 11**: Comprehensive GitHub API and token testing
- Checks configuration
- Tests connectivity
- Verifies authentication

Run both with:
```bash
./init-setup.sh
```

## For More Details

See [LLM_AND_GITHUB_TESTING.md](LLM_AND_GITHUB_TESTING.md) for:
- Detailed test explanations
- Comprehensive troubleshooting
- Security best practices
- CI/CD integration examples

## Scripts Location

- LLM testing: `scripts/test-llm-keys.py`
- GitHub testing: `scripts/test-github-token.py`
- Main init: `./init-setup.sh`
- Documentation: `LLM_AND_GITHUB_TESTING.md`
