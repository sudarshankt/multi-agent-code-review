#!/usr/bin/env python3
"""
Comprehensive LLM API Key Testing and Verification Script

Tests all configured LLM providers to ensure:
1. API keys are set
2. API connectivity works
3. Models are accessible
4. LLM service can generate completions
"""

import sys
import os
from typing import Optional, Dict, Any
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import get_settings
from src.core.logging import get_logger, configure_logging

logger = get_logger(__name__)


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str) -> None:
    """Print a formatted header"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.END}\n")


def print_success(text: str) -> None:
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.END} {text}")


def print_error(text: str) -> None:
    """Print error message"""
    print(f"{Colors.RED}✗{Colors.END} {text}")


def print_warning(text: str) -> None:
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.END} {text}")


def print_info(text: str) -> None:
    """Print info message"""
    print(f"{Colors.BLUE}ℹ{Colors.END} {text}")


def test_anthropic_api() -> bool:
    """Test Anthropic API connectivity"""
    print_info("Testing Anthropic API...")
    
    settings = get_settings()
    api_key = settings.llm_api_key
    
    if not api_key:
        print_error("ANTHROPIC_API_KEY not configured")
        return False
    
    try:
        from langchain_anthropic import ChatAnthropic
        
        # Initialize client
        client = ChatAnthropic(
            api_key=api_key,
            model=settings.primary_model,
            timeout=10,
            max_retries=1,
        )
        
        # Test with a simple message
        response = client.invoke([
            {"role": "user", "content": "Reply with exactly: WORKING"}
        ])
        
        if response and "WORKING" in str(response.content):
            print_success(f"Anthropic API working with model: {settings.primary_model}")
            return True
        else:
            print_error(f"Unexpected response from Anthropic: {response.content}")
            return False
            
    except Exception as e:
        print_error(f"Anthropic API test failed: {str(e)}")
        return False


def test_anthropic_api_provider() -> bool:
    """Test Anthropic provider API connectivity"""
    print_info("Testing Anthropic API (via provider)...")
    
    settings = get_settings()
    api_key = settings.llm_api_key
    
    if not api_key:
        print_error("ANTHROPIC_API_KEY not configured")
        return False
    
    try:
        from langchain_anthropic import ChatAnthropic
        
        client = ChatAnthropic(
            api_key=api_key,
            model="claude-3-5-sonnet-20241022",
            timeout=10,
            max_retries=1,
        )
        
        response = client.invoke([
            {"role": "user", "content": "Reply with exactly: WORKING"}
        ])
        
        if response and "WORKING" in str(response.content):
            print_success("Anthropic API working with model: claude-3-5-sonnet-20241022")
            return True
        else:
            print_error(f"Unexpected response from Anthropic: {response.content}")
            return False
            
    except Exception as e:
        print_warning(f"Anthropic API test skipped or failed: {str(e)}")
        return False


def test_openai_api() -> bool:
    """Test OpenAI API connectivity"""
    print_info("Testing OpenAI API...")
    
    api_key = os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        print_warning("OPENAI_API_KEY not configured (skipping OpenAI test)")
        return True  # Not a failure
    
    try:
        from langchain_openai import ChatOpenAI
        
        client = ChatOpenAI(
            api_key=api_key,
            model="gpt-4o-mini",
            timeout=10,
            max_retries=1,
        )
        
        response = client.invoke([
            {"role": "user", "content": "Reply with exactly: WORKING"}
        ])
        
        if response and "WORKING" in str(response.content):
            print_success("OpenAI API working with model: gpt-4o-mini")
            return True
        else:
            print_error(f"Unexpected response from OpenAI: {response.content}")
            return False
            
    except Exception as e:
        print_warning(f"OpenAI API test failed or key invalid: {str(e)}")
        return False


def test_deepseek_api() -> bool:
    """Test DeepSeek API connectivity"""
    print_info("Testing DeepSeek API...")
    
    settings = get_settings()
    api_key = settings.llm_api_key
    
    if not api_key:
        print_error("LLM_API_KEY not configured for DeepSeek")
        return False
    
    if not settings.llm_base_url:
        print_error("LLM_BASE_URL not configured for DeepSeek")
        return False
    
    try:
        from langchain_anthropic import ChatAnthropic
        
        # DeepSeek uses Anthropic API format with custom base URL
        client = ChatAnthropic(
            api_key=api_key,
            base_url=settings.llm_base_url,
            model=settings.primary_model,
            timeout=10,
            max_retries=1,
        )
        
        # Test with a simple message
        response = client.invoke([
            {"role": "user", "content": "Reply with exactly: WORKING"}
        ])
        
        if response and "WORKING" in str(response.content):
            print_success(f"DeepSeek API working with model: {settings.primary_model}")
            print_info(f"  Base URL: {settings.llm_base_url}")
            return True
        else:
            print_error(f"Unexpected response from DeepSeek: {response.content}")
            return False
            
    except Exception as e:
        print_warning(f"DeepSeek API test failed: {str(e)}")
        return False


def test_llm_service() -> bool:
    """Test the LLMService wrapper"""
    import asyncio
    print_info("Testing LLMService wrapper...")
    
    try:
        from src.services.llm_service import LLMService
        
        async def _test_async():
            llm_service = LLMService()
            
            # Try to use the service
            result = await llm_service.complete(
                prompt="Say WORKING"
            )
            return result
        
        result = asyncio.run(_test_async())
        
        if result and len(result) > 0:
            print_success("LLMService wrapper working correctly")
            print_info(f"  Response: {result[:100]}...")
            return True
        else:
            print_error(f"LLMService returned empty result")
            return False
            
    except Exception as e:
        print_error(f"LLMService test failed: {str(e)}")
        return False


def validate_environment() -> bool:
    """Validate LLM environment configuration"""
    print_header("PHASE 1: ENVIRONMENT VALIDATION")
    
    settings = get_settings()
    all_valid = True
    
    # Check API key
    print_info("Checking API key configuration...")
    if not settings.llm_api_key:
        print_error("LLM_API_KEY is not set (REQUIRED)")
        all_valid = False
    elif len(settings.llm_api_key) < 10:
        print_error("LLM_API_KEY appears to be invalid (too short)")
        all_valid = False
    else:
        masked_key = settings.llm_api_key[:10] + "..." + settings.llm_api_key[-5:]
        print_success(f"LLM_API_KEY is set: {masked_key}")
    
    # Check provider
    print_info(f"LLM Provider: {settings.model_provider}")
    if settings.model_provider not in ["anthropic", "deepseek"]:
        print_warning(f"Unknown provider: {settings.model_provider}")
    
    # Check models
    print_info(f"Primary Model: {settings.primary_model}")
    print_info(f"Fallback Model: {settings.fallback_model}")
    
    # Check base URL (if needed)
    if settings.model_provider == "deepseek" and settings.llm_base_url:
        print_success(f"DeepSeek Base URL: {settings.llm_base_url}")
    elif settings.model_provider == "deepseek":
        print_warning("DeepSeek base URL not configured")
    
    # Check SSL certificate
    if settings.ssl_cert_file:
        if os.path.exists(settings.ssl_cert_file):
            print_success(f"SSL Certificate found: {settings.ssl_cert_file}")
        else:
            print_error(f"SSL Certificate not found: {settings.ssl_cert_file}")
            all_valid = False
    
    return all_valid


def test_connectivity() -> bool:
    """Test LLM API connectivity for all configured providers"""
    print_header("PHASE 2: LLM CONNECTIVITY TESTS")
    
    settings = get_settings()
    all_working = True
    
    if not settings.llm_api_key:
        print_error("Cannot test connectivity without API key")
        return False
    
    # Test based on configured provider
    if settings.model_provider == "deepseek":
        print_info("Primary provider: DeepSeek")
        if not test_deepseek_api():
            all_working = False
    elif settings.model_provider == "anthropic":
        print_info("Primary provider: Anthropic")
        if not test_anthropic_api_provider():
            all_working = False
    else:
        print_warning(f"Unknown provider: {settings.model_provider}")
        all_working = False
    
    # Also test other providers if available
    print_info("Testing other available providers...")
    if test_openai_api():
        pass  # OpenAI tested
    else:
        print_info("OpenAI not available (OPENAI_API_KEY not set)")
    
    # Always test the service wrapper
    if not test_llm_service():
        all_working = False
    
    return all_working


def test_fallback_model() -> bool:
    """Test fallback model if different from primary"""
    print_header("PHASE 3: FALLBACK MODEL TEST")
    
    settings = get_settings()
    
    if settings.fallback_model == settings.primary_model:
        print_info("Fallback model same as primary, skipping separate test")
        return True
    
    print_info(f"Testing fallback model: {settings.fallback_model}")
    
    try:
        from langchain_anthropic import ChatAnthropic
        
        client = ChatAnthropic(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url or "https://api.anthropic.com",
            model=settings.fallback_model,
            timeout=10,
            max_retries=1,
        )
        
        response = client.invoke([
            {"role": "user", "content": "Say OK"}
        ])
        
        if response:
            print_success(f"Fallback model {settings.fallback_model} is accessible")
            return True
        else:
            print_error(f"Fallback model returned no response")
            return False
            
    except Exception as e:
        print_error(f"Fallback model test failed: {str(e)}")
        return False


def test_model_parameters() -> bool:
    """Test LLM service with various parameters"""
    import asyncio
    print_header("PHASE 4: MODEL PARAMETERS TEST")
    
    try:
        from src.services.llm_service import LLMService
        
        async def _test_async():
            llm = LLMService()
            
            # Test with different prompts
            print_info("Testing basic completion...")
            result = await llm.complete(
                prompt="Count to 3"
            )
            if not result:
                return False
            print_success("Basic completion works")
            
            # Test with system prompt
            print_info("Testing with system prompt...")
            result = await llm.complete(
                prompt="What's 2+2?",
                system="You are a math tutor. Be concise."
            )
            if not result:
                return False
            print_success("System prompt works")
            
            # Test JSON extraction
            print_info("Testing JSON extraction...")
            result = await llm.complete_json(
                prompt='Return this JSON: {"status": "ok", "count": 42}'
            )
            if isinstance(result, dict) and "status" in result:
                print_success("JSON extraction works")
            else:
                print_warning(f"JSON extraction returned: {result}")
            
            return True
        
        success = asyncio.run(_test_async())
        return success
        
    except Exception as e:
        print_error(f"Model parameters test failed: {str(e)}")
        return False


def generate_report(results: Dict[str, bool]) -> None:
    """Generate final test report"""
    print_header("FINAL TEST REPORT")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"{Colors.BOLD}Test Results:{Colors.END}")
    for test_name, result in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.END}" if result else f"{Colors.RED}✗ FAIL{Colors.END}"
        print(f"  {status} - {test_name}")
    
    print(f"\n{Colors.BOLD}Summary:{Colors.END}")
    print(f"  Passed: {Colors.GREEN}{passed}/{total}{Colors.END}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ ALL LLM TESTS PASSED{Colors.END}")
        print(f"{Colors.GREEN}Your LLM is properly configured and working!{Colors.END}\n")
        return True
    else:
        failed = total - passed
        print(f"\n{Colors.RED}{Colors.BOLD}✗ {failed} TEST(S) FAILED{Colors.END}")
        print(f"{Colors.RED}Please check the errors above and fix your configuration.{Colors.END}\n")
        return False


def main() -> int:
    """Main test runner"""
    configure_logging()
    
    print_header("LLM API KEY TESTING & VERIFICATION")
    print(f"Testing comprehensive LLM configuration and connectivity\n")
    
    results: Dict[str, bool] = {}
    
    # Phase 1: Environment validation
    try:
        results["Environment Validation"] = validate_environment()
    except Exception as e:
        print_error(f"Environment validation failed: {str(e)}")
        results["Environment Validation"] = False
    
    # Phase 2: Connectivity tests
    try:
        results["LLM Connectivity"] = test_connectivity()
    except Exception as e:
        print_error(f"Connectivity test failed: {str(e)}")
        results["LLM Connectivity"] = False
    
    # Phase 3: Fallback model test
    try:
        results["Fallback Model"] = test_fallback_model()
    except Exception as e:
        print_error(f"Fallback model test failed: {str(e)}")
        results["Fallback Model"] = False
    
    # Phase 4: Model parameters test
    try:
        results["Model Parameters"] = test_model_parameters()
    except Exception as e:
        print_error(f"Model parameters test failed: {str(e)}")
        results["Model Parameters"] = False
    
    # Generate report
    success = generate_report(results)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
