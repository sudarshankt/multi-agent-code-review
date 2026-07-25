# LLM & GitHub Integration Testing Guide

This document explains the comprehensive LLM and GitHub API testing scripts that verify all external integrations with API keys and tokens.

## Overview

The system supports multiple LLM providers (Anthropic, DeepSeek, etc.) and GitHub integration. This guide explains how to test these integrations independently and as part of the initialization process.

## LLM Testing Script

### Location
```
scripts/test-llm-keys.py
```

### What It Tests
1. **Environment Validation** - Checks LLM configuration from .env
2. **LLM Connectivity** - Tests direct API connectivity
3. **LLMService Wrapper** - Tests the system's LLM service wrapper
4. **Model Parameters** - Tests various LLM operations (completions, JSON extraction)
5. **Fallback Model** - Verifies fallback model if different from primary

### Running the LLM Tests

```bash
# From workspace root with venv activated
python scripts/test-llm-keys.py
```

### Test Phases Explained

#### Phase 1: Environment Validation
- Checks if `LLM_API_KEY` is set
- Validates API key format (not too short)
- Identifies LLM provider (anthropic/deepseek)
- Checks primary and fallback models
- Verifies base URL for custom gateways (DeepSeek)
- Checks SSL certificate if configured

**Why it matters**: Configuration issues should be caught early before attempting API calls.

#### Phase 2: LLM Connectivity
- **DeepSeek API Test**: Tests direct connectivity to DeepSeek API
  - Uses your API key to authenticate
  - Sends a simple completion request
  - Verifies response is valid
  
- **LLMService Wrapper Test**: Tests the system's LLM service
  - Initializes LLMService with your configuration
  - Sends async completion request
  - Verifies service works end-to-end

**Why it matters**: Ensures API keys are valid and your provider is accessible.

#### Phase 3: Fallback Model Test
- If fallback model differs from primary, tests it separately
- Skipped if using same model for both

**Why it matters**: Ensures fallback model is available in case primary fails.

#### Phase 4: Model Parameters Test
- **Basic Completion**: Tests simple text generation
- **System Prompt**: Tests with system context/instructions
- **JSON Extraction**: Tests JSON parsing from LLM responses

**Why it matters**: Verifies the LLM works with the specific patterns used by agents.

### Example Output

```
======================================================================
LLM API KEY TESTING & VERIFICATION
======================================================================

✓ PASS - Environment Validation
✓ PASS - LLM Connectivity
✓ PASS - Fallback Model
✓ PASS - Model Parameters

Passed: 4/4
✓ ALL LLM TESTS PASSED
Your LLM is properly configured and working!
```

### Troubleshooting LLM Tests

#### "LLM_API_KEY is not set (REQUIRED)"
**Problem**: `LLM_API_KEY` environment variable not found
**Solution**:
1. Check your `.env` file: `cat .env | grep LLM_API_KEY`
2. If missing, add it: `echo "LLM_API_KEY=sk-your-api-key" >> .env`
3. Re-run test

#### "API test failed: 401 Unauthorized"
**Problem**: API key is invalid or expired
**Solution**:
1. Verify your API key from your provider's console
2. Check for typos: `echo $LLM_API_KEY`
3. Update `.env` with correct key
4. Re-run test

#### "Connection timeout"
**Problem**: Can't reach the API endpoint
**Solution**:
1. Check internet connectivity: `ping api.deepseek.com` (for DeepSeek)
2. Verify base URL: `echo $LLM_BASE_URL`
3. Check firewall/proxy settings

#### "LLMService test failed"
**Problem**: Service wrapper error
**Solution**:
1. Check all dependencies installed: `pip list | grep langchain`
2. Verify Python version: `python --version` (needs 3.10+)
3. Check for circular imports in logs

## GitHub Testing Script

### Location
```
scripts/test-github-token.py
```

### What It Tests
1. **GitHub Configuration** - Checks GitHub API settings
2. **GitHub Service** - Tests GitHubService initialization
3. **API Connectivity** - Tests API endpoint reachability

### Running the GitHub Tests

```bash
# From workspace root with venv activated
python scripts/test-github-token.py
```

### Test Phases Explained

#### Phase 1: GitHub Configuration Validation
- Checks if GitHub API base URL is configured (default: https://api.github.com)
- Checks if GITHUB_TOKEN is set (optional but recommended)
- Masks token in output for security
- Verifies SSL CA bundle if configured (enterprise)

**Why it matters**: Configuration should be correct before attempting API calls.

**Note**: Token is optional. Without it, you can use GitHub API for public repos with rate limiting.

#### Phase 2: GitHub Service Test
- Initializes GitHubService class
- Checks authentication readiness
- Verifies service can be instantiated

**Why it matters**: Confirms the service layer is properly configured.

#### Phase 3: API Connectivity
- Tests connectivity to GitHub API endpoint
- Accepts 200, 401, 403, 404 as valid responses (meaning API is reachable)
- Diagnoses authentication/permission issues

**Why it matters**: Ensures GitHub API is accessible from your network.

### Example Output

```
======================================================================
GITHUB API & TOKEN VERIFICATION
======================================================================

✓ PASS - Environment Configuration
✓ PASS - GitHub Service
✓ PASS - API Connectivity

Passed: 3/3
✓ GITHUB VERIFICATION COMPLETE
GitHub integration is fully configured and working!
```

### Troubleshooting GitHub Tests

#### "GitHub token is not set"
**Note**: This is a warning, not an error. The system works without a token.
**To enable token-based access**:
1. Generate token at https://github.com/settings/tokens
2. Add to `.env`: `GITHUB_TOKEN=ghp_your_token_here`
3. Re-run test

#### "API connectivity test failed"
**Problem**: Can't reach GitHub API
**Solution**:
1. Check internet: `ping api.github.com`
2. Verify firewall allows HTTPS
3. Check proxy settings if behind corporate proxy

#### "Unauthorized (401)"
**Problem**: Token is invalid or expired
**Solution**:
1. Verify token at https://github.com/settings/tokens
2. Check token hasn't expired
3. Regenerate if needed and update `.env`

## Combined Testing

### Running Both LLM and GitHub Tests
```bash
# LLM tests
python scripts/test-llm-keys.py

# GitHub tests
python scripts/test-github-token.py
```

### Or Use the Comprehensive Init Script
```bash
./init-setup.sh
```
This runs both test suites as part of Phase 10 and Phase 11 of initialization.

## Environment Variables Reference

### Required for LLM
- `LLM_API_KEY` - Your LLM provider's API key
  - **Type**: string (secret)
  - **Example**: `sk-95483ea...3acaa`
  - **Where to get**: Your LLM provider's console

### Optional for LLM
- `PRIMARY_MODEL` - Primary model to use (default: deepseek-v4-pro)
- `FALLBACK_MODEL` - Fallback model if primary fails (default: deepseek-v4-pro)
- `LLM_BASE_URL` - Custom API gateway (default: https://api.deepseek.com/anthropic)
- `MODEL_PROVIDER` - Provider type: "anthropic" or "deepseek" (default: deepseek)
- `LLM_MAX_TOKENS` - Maximum tokens per response (default: 4096)
- `LLM_TIMEOUT_SECONDS` - Request timeout (default: 120)
- `SSL_CERT_FILE` - Path to SSL certificate (enterprise only)

### Optional for GitHub
- `GITHUB_TOKEN` - Your GitHub personal access token
  - **Type**: string (secret)
  - **Example**: `ghp_WhmTDW...Zsotk`
  - **Where to get**: https://github.com/settings/tokens
  - **Scope needed**: `repo`, `read:user`

- `GITHUB_API_BASE_URL` - GitHub API base URL (default: https://api.github.com)
  - **For GitHub Enterprise**: `https://github.enterprise.com/api/v3`

- `GITHUB_WEBHOOK_SECRET` - For webhook verification (optional)
- `GITHUB_CA_BUNDLE` - Custom CA bundle for enterprise (optional)

## Integration with init-setup.sh

The comprehensive initialization script now includes LLM and GitHub testing:

**Phase 10: LLM Service Verification**
```bash
python scripts/test-llm-keys.py
```

**Phase 11: GitHub Service Verification**
```bash
python scripts/test-github-token.py
```

These phases are performed after all services are running, ensuring complete verification.

## Best Practices

1. **Test Early**: Run tests immediately after updating `.env`
2. **Test After Changes**: If you change API keys, re-run tests
3. **Regular Verification**: Run `./init-setup.sh` regularly to verify continued health
4. **Monitor Logs**: Check logs for detailed error information
5. **Rotate Keys**: Update API keys periodically in `.env`

## API Key Security

⚠️ **Important**:
- Never commit `.env` to version control
- Never share API keys in logs or error messages
- Rotate keys periodically
- Use `.env.example` as a template (never expose real keys)
- Store keys in secure vaults or CI/CD secrets management

## Testing in CI/CD

To use these tests in CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Test LLM Integration
  env:
    LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    source .venv/bin/activate
    python scripts/test-llm-keys.py
    python scripts/test-github-token.py
```

## Performance Considerations

- **LLM Tests**: Each test makes 1-2 API calls, ~2-5 seconds per test
- **GitHub Tests**: Quick connectivity checks, ~1 second total
- **Total Time**: Both suites together, ~15-30 seconds depending on network

## Support & Issues

If tests fail:

1. Check the detailed error messages
2. Verify all required environment variables are set
3. Check internet connectivity
4. Review API provider status pages
5. Check API key quotas/limits
6. Consult troubleshooting sections above

## Related Documentation

- [QUICKSTART.md](../QUICKSTART.md) - Quick start guide
- [INIT_VERIFICATION.md](../INIT_VERIFICATION.md) - Detailed initialization phases
- [init-setup.sh](../init-setup.sh) - Main initialization script
