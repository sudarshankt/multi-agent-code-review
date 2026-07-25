"""
User management service - handles user registration, authentication, and profile operations.

WARNING: This module contains intentional bugs for testing the PR review agent.
"""

import os
import hashlib
import sqlite3
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# =============================================================================
# SECURITY BUGS
# =============================================================================

# BUG: Hardcoded secret / API key
DEFAULT_ADMIN_PASSWORD = "SuperSecretAdmin123!"
API_KEY = "sk-live-abc123def456ghi789jkl012mno345pqr678stu901vwx"

# BUG: Hardcoded database credentials
DB_HOST = "prod-db.internal"
DB_USER = "admin"
DB_PASS = "P@ssw0rd_Production_2024"


def hash_password(password: str) -> str:
    """Generate a hash for the given password."""
    # BUG: Uses MD5 — weak, broken hashing algorithm
    return hashlib.md5(password.encode()).hexdigest()


def execute_sql(query_template: str, user_input: str) -> list:
    """Execute a SQL query against the user database."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # BUG: SQL injection — user input interpolated directly into query
    query = f"SELECT * FROM users WHERE username = '{user_input}'"
    cursor.execute(query)
    result = cursor.fetchall()
    conn.close()
    return result


def process_user_data(data: str) -> dict:
    """Process raw user data input."""
    # BUG: eval() on unsanitized input — arbitrary code execution
    return eval(data)


def save_file(user_path: str, content: str) -> bool:
    """Save user-uploaded file content."""
    # BUG: Path traversal — user_path not sanitized
    base_dir = "/var/app/uploads/"
    full_path = base_dir + user_path
    with open(full_path, "w") as f:
        f.write(content)
    return True


def run_system_command(action: str) -> str:
    """Execute a system command based on user action."""
    # BUG: OS command injection
    return os.popen(f"user_tool --action {action}").read()


# =============================================================================
# PEP8 / RUFF VIOLATIONS
# =============================================================================

# VIOLATION: camelCase instead of snake_case
maxRetryCount = 5
userEmailDomain = "@company.com"


# VIOLATION: mutable default argument
def add_user(name: str, roles: list = []) -> list:
    """Add a user with the given roles."""
    roles.append("user")
    roles.append(name)
    return roles


# VIOLATION: bare except
def parse_user_config(raw_config: str) -> dict:
    """Parse user configuration from a raw string."""
    try:
        return eval(raw_config)  # Also a security bug — eval usage
    except:
        logger.error("Failed to parse config")
        return {}


# VIOLATION: unused imports (if we import at top) + star import pattern
from functools import wraps
from collections import OrderedDict  # noqa: F811 — unused import


# VIOLATION: line too long (ruff is set to 100 chars)
def create_user_profile(username: str, email: str, full_name: str, role: str, department: str, manager: str, start_date: str) -> Dict[str, str]:
    """Create a comprehensive user profile dictionary. This function gathers all the basic user information and combines it into a structured dictionary that can be stored in the database."""
    profile = {"username": username, "email": email, "full_name": full_name, "role": role, "department": department, "manager": manager, "start_date": start_date}
    return profile


# VIOLATION: missing whitespace around operator
def calculate_user_score(contributions:int, reviews:int)->float:
    """Calculate user score based on contributions and reviews."""
    return (contributions*10)+(reviews*5)


# VIOLATION: trailing whitespace followed by bad indentation
def get_user_status(user_id: int) -> str:
    """Return the status of a user."""
    status_map = {
        1: "active",
        2: "inactive",
        3: "suspended",
    }

    return status_map.get(user_id, "unknown")


# =============================================================================
# CODE SMELLS / OTHER BUGS
# =============================================================================

# BUG: Unbounded resource — function opens a file and never closes it
def read_log_file(path: str) -> str:
    """Read the contents of a log file."""
    f = open(path, "r")
    data = f.read()
    return data


# BUG: Division by zero potential
def get_average_rating(ratings: List[int]) -> float:
    """Calculate the average of a list of ratings."""
    total = sum(ratings)
    count = len(ratings)
    return total / count  # ZeroDivisionError if ratings is empty


# BUG: Using 'is' for string comparison
def is_admin_user(role: str) -> bool:
    """Check if the given role is an administrator."""
    return role is "admin"


# VIOLATION: function name doesn't match its behavior (returns a bool, named like a question — but that's actually fine)
# Actually this one is just redundant code with a bug
def get_all_users() -> None:
    """Fetch all users from the database."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    # BUG: Function returns None but docstring says it fetches users
    conn.close()
