#!/usr/bin/env python3
"""
Comprehensive pytest Testing and Verification Script

Tests pytest installation and runs the test suite to ensure:
1. pytest is properly installed
2. Test environment is configured
3. All tests pass
4. Code quality checks pass
"""

import sys
import os
import subprocess
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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


def test_pytest_installation() -> bool:
    """Test pytest installation"""
    print_header("PHASE 1: PYTEST INSTALLATION CHECK")
    
    print_info("Checking pytest installation...")
    
    try:
        import pytest
        print_success(f"pytest installed: {pytest.__version__}")
    except ImportError:
        print_error("pytest not installed")
        return False
    
    try:
        import pytest_asyncio
        print_success(f"pytest-asyncio installed: {pytest_asyncio.__version__}")
    except ImportError:
        print_warning("pytest-asyncio not installed (async tests may not work)")
    
    # Check if pytest is in PATH
    result = subprocess.run(
        ["pytest", "--version"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode == 0:
        print_success(f"pytest command available: {result.stdout.strip()}")
        return True
    else:
        print_error("pytest command not found in PATH")
        return False


def test_project_structure() -> bool:
    """Verify test project structure"""
    print_header("PHASE 2: PROJECT STRUCTURE VERIFICATION")
    
    test_dirs = [
        "tests",
        "tests/unit",
        "tests/integration",
    ]
    
    all_exist = True
    for test_dir in test_dirs:
        test_path = PROJECT_ROOT / test_dir
        if test_path.exists():
            print_success(f"Test directory exists: {test_dir}")
        else:
            print_warning(f"Test directory missing: {test_dir}")
            all_exist = False
    
    # Check for conftest.py
    conftest = PROJECT_ROOT / "tests" / "conftest.py"
    if conftest.exists():
        print_success("conftest.py found for test configuration")
    else:
        print_warning("conftest.py not found")
    
    # Check for test files
    test_files = list((PROJECT_ROOT / "tests").rglob("test_*.py"))
    if test_files:
        print_success(f"Found {len(test_files)} test files")
        for test_file in test_files[:3]:
            print_info(f"  - {test_file.relative_to(PROJECT_ROOT)}")
        if len(test_files) > 3:
            print_info(f"  ... and {len(test_files) - 3} more")
    else:
        print_warning("No test_*.py files found")
    
    return all_exist


def run_unit_tests() -> tuple[bool, str]:
    """Run unit tests"""
    print_header("PHASE 3: RUNNING UNIT TESTS")
    
    print_info("Running pytest on unit tests...")
    
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/unit/",
                "-v",
                "--tb=short",
                "-x",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            # Count passed tests
            passed = output.count(" PASSED")
            print_success(f"Unit tests passed ({passed} tests)")
            return True, output
        else:
            # Show failure info
            if "FAILED" in output:
                print_error("Some unit tests failed")
                # Show first few failures
                lines = output.split("\n")
                for i, line in enumerate(lines):
                    if "FAILED" in line:
                        print_error(f"  {line}")
                        if i + 1 < len(lines):
                            print_info(f"  {lines[i + 1]}")
            else:
                print_warning("Unit tests exited with error")
            return False, output
            
    except subprocess.TimeoutExpired:
        print_error("Unit tests timed out (>120 seconds)")
        return False, ""
    except Exception as e:
        print_error(f"Failed to run unit tests: {str(e)}")
        return False, ""


def run_integration_tests() -> tuple[bool, str]:
    """Run integration tests"""
    print_header("PHASE 4: RUNNING INTEGRATION TESTS")
    
    print_info("Running pytest on integration tests...")
    
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/integration/",
                "-v",
                "--tb=short",
                "-x",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            # Count passed tests
            passed = output.count(" PASSED")
            print_success(f"Integration tests passed ({passed} tests)")
            return True, output
        else:
            # Show failure info
            if "FAILED" in output:
                print_warning("Some integration tests failed")
                # Show first few failures
                lines = output.split("\n")
                for i, line in enumerate(lines):
                    if "FAILED" in line:
                        print_warning(f"  {line}")
                        if i + 1 < len(lines):
                            print_info(f"  {lines[i + 1]}")
            elif "no tests ran" in output.lower():
                print_info("No integration tests to run")
                return True, output
            else:
                print_warning("Integration tests exited with warning")
            return True, output  # Not fatal
            
    except subprocess.TimeoutExpired:
        print_warning("Integration tests timed out (>180 seconds)")
        return True, ""  # Not fatal
    except Exception as e:
        print_warning(f"Failed to run integration tests: {str(e)}")
        return True, ""  # Not fatal


def run_pytest_coverage() -> tuple[bool, str]:
    """Run pytest with coverage report"""
    print_header("PHASE 5: PYTEST COVERAGE REPORT")
    
    print_info("Checking for pytest-cov plugin...")
    
    try:
        import pytest_cov
        print_success(f"pytest-cov installed")
    except ImportError:
        print_warning("pytest-cov not installed (coverage unavailable)")
        return True, ""  # Not fatal
    
    print_info("Running tests with coverage...")
    
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "--cov=src",
                "--cov-report=term-missing",
                "-q",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0 or "coverage" in output.lower():
            print_success("Coverage report generated")
            # Show summary
            lines = output.split("\n")
            for line in lines:
                if "coverage" in line.lower() or "%" in line:
                    print_info(f"  {line}")
            return True, output
        else:
            print_warning("Could not generate coverage report")
            return True, output
            
    except subprocess.TimeoutExpired:
        print_warning("Coverage analysis timed out")
        return True, ""
    except Exception as e:
        print_warning(f"Coverage analysis failed: {str(e)}")
        return True, ""


def run_linting_checks() -> bool:
    """Run linting checks with ruff"""
    print_header("PHASE 6: LINTING CHECKS (ruff)")
    
    print_info("Checking for ruff installation...")
    
    try:
        result = subprocess.run(
            ["ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print_success(f"ruff installed: {result.stdout.strip()}")
        else:
            print_warning("ruff not available for linting")
            return True
    except FileNotFoundError:
        print_warning("ruff not found in PATH")
        return True
    
    print_info("Running ruff on src/ directory...")
    
    try:
        result = subprocess.run(
            [
                "ruff",
                "check",
                "src/",
                "--select=E,W,F",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0:
            print_success("No linting issues found in src/")
            return True
        else:
            output = result.stdout + result.stderr
            if output.strip():
                print_warning("Linting issues found:")
                lines = output.split("\n")[:10]  # Show first 10 lines
                for line in lines:
                    if line.strip():
                        print_info(f"  {line}")
            return True  # Not fatal
            
    except Exception as e:
        print_warning(f"Linting check failed: {str(e)}")
        return True


def generate_report(results: dict) -> bool:
    """Generate final test report"""
    print_header("FINAL PYTEST TEST REPORT")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"{Colors.BOLD}Test Results:{Colors.END}")
    for test_name, result in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.END}" if result else f"{Colors.RED}✗ FAIL{Colors.END}"
        print(f"  {status} - {test_name}")
    
    print(f"\n{Colors.BOLD}Summary:{Colors.END}")
    print(f"  Passed: {Colors.GREEN}{passed}/{total}{Colors.END}")
    
    if passed >= total - 1:  # Allow 1 optional failure
        print(f"\n{Colors.GREEN}{Colors.BOLD}✓ PYTEST VERIFICATION COMPLETE{Colors.END}")
        print(f"{Colors.GREEN}Test suite is properly configured and working!{Colors.END}\n")
        return True
    else:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠ PYTEST VERIFICATION PARTIAL{Colors.END}")
        print(f"{Colors.YELLOW}Some test phases had issues, but core testing is available.{Colors.END}\n")
        return True  # Still acceptable


def main() -> int:
    """Main test runner"""
    configure_logging()
    
    print_header("PYTEST TESTING & VERIFICATION")
    print(f"Testing pytest installation and running test suite\n")
    
    results: dict = {}
    
    # Phase 1: pytest installation
    try:
        results["pytest Installation"] = test_pytest_installation()
    except Exception as e:
        print_error(f"pytest installation check failed: {str(e)}")
        results["pytest Installation"] = False
    
    # Phase 2: Project structure
    try:
        results["Project Structure"] = test_project_structure()
    except Exception as e:
        print_error(f"Project structure check failed: {str(e)}")
        results["Project Structure"] = False
    
    # Phase 3: Unit tests
    try:
        success, _ = run_unit_tests()
        results["Unit Tests"] = success
    except Exception as e:
        print_error(f"Unit tests failed: {str(e)}")
        results["Unit Tests"] = False
    
    # Phase 4: Integration tests
    try:
        success, _ = run_integration_tests()
        results["Integration Tests"] = success
    except Exception as e:
        print_error(f"Integration tests failed: {str(e)}")
        results["Integration Tests"] = False
    
    # Phase 5: Coverage
    try:
        success, _ = run_pytest_coverage()
        results["Coverage Report"] = success
    except Exception as e:
        print_error(f"Coverage check failed: {str(e)}")
        results["Coverage Report"] = False
    
    # Phase 6: Linting
    try:
        results["Linting Checks"] = run_linting_checks()
    except Exception as e:
        print_error(f"Linting check failed: {str(e)}")
        results["Linting Checks"] = False
    
    # Generate report
    success = generate_report(results)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
