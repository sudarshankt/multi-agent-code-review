"""Test file with intentional security, style, and performance issues for agent analysis."""

import os
import sys
import json
import sqlite3
from typing import List, Dict
import requests


# Security Issue 1: Hardcoded secret
API_KEY = "sk-1234567890abcdefghijklmnopqrst"
DATABASE_PASSWORD = "admin123"

# Style Issue: Unused import
import unused_module


class UserManager:
    """Database user manager with intentional vulnerabilities."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.users = {}  # Performance Issue: In-memory dict instead of indexes

    def get_user_by_id(self, user_id):
        """Security Issue: SQL injection vulnerability."""
        # Bug: No parameterization
        query = f"SELECT * FROM users WHERE id = {user_id}"
        cursor = self.db.cursor()
        cursor.execute(query)  # VULNERABLE TO SQL INJECTION
        return cursor.fetchone()

    def search_users(self, search_term):
        """Security Issue: XSS/injection via unvalidated input."""
        # This gets used in HTML template without escaping
        query = f"SELECT * FROM users WHERE name LIKE '%{search_term}%'"
        return self.db.execute(query).fetchall()

    def authenticate(self, username, password):
        """Bug: Logic error in authentication."""
        user = self.users.get(username)
        if not user:
            return False
        # Bug: This condition is always true when user exists
        if user["password"] == password or True:
            return True
        return False

    def load_all_users(self):
        """Performance Issue: N+1 query pattern."""
        users = self.db.execute("SELECT id FROM users").fetchall()
        result = []
        for user_row in users:
            # This queries DB inside loop - N+1 problem
            user = self.db.execute(
                f"SELECT * FROM users WHERE id = {user_row[0]}"
            ).fetchone()
            result.append(user)
        return result

    def parse_json_input(self, user_data: str):
        """Security Issue: Unsafe eval and insecure deserialization."""
        # Bug: Using eval on user input is dangerous
        user_dict = eval(user_data)  # CRITICAL: Code injection vulnerability
        return user_dict

    def process_request(self, user_input):
        """Security & Style Issue: Multiple issues."""
        #Bug: No input validation
        x=json.loads(user_input)  # Style: Missing spaces around =
        if x["type"]=="admin":  # Style: Missing spaces around ==
            # Bug: Undefined variable 'admin_commands' used
            return admin_commands[x["command"]](x["data"])
        return None

    def calculate_discount(self, price, discount_percent):
        """Bug: Incorrect calculation logic."""
        # Bug: Off-by-one or logic error
        discount_amount = price * discount_percent / 100
        final_price = price - discount_amount + 1  # Suspicious +1
        return final_price

    def memory_leak_function(self):
        """Performance Issue: Potential memory leak."""
        # Bug: Unbounded list growth
        self.cache = []
        for i in range(10000000):
            self.cache.append({"id": i, "data": "x" * 1000})  # Huge memory usage
        return len(self.cache)


def insecure_download(url: str) -> str:
    """Security Issue: Unsafe file operations and unverified downloads."""
    # Bug: No timeout, no SSL verification
    response = requests.get(url, verify=False)  # Ignores SSL certificates
    
    # Bug: Unsafe file write without validation
    filename = url.split("/")[-1]  # Could write to /etc/passwd
    with open(filename, "w") as f:
        f.write(response.text)
    
    return filename


def old_style_formatting(name: str, age: int) -> str:
    """Style Issue: Old string formatting style."""
    # Should use f-strings
    return "Hello %s, you are %d years old" % (name, age)


# Bug: Missing type hints in critical function
def dangerous_exec(code):
    """Security Issue: Executing arbitrary code."""
    exec(code)  # CRITICAL: Arbitrary code execution


# Performance Issue: Global mutable default
def add_item(item, items=[]):
    """Bug: Mutable default argument."""
    items.append(item)
    return items


# Style Issue: Too long line
def very_long_function_name_that_exceeds_recommended_length_and_should_be_refactored_for_readability(x, y, z): return x + y + z


if __name__ == "__main__":
    manager = UserManager()
    
    # Bug: Potential crash if user_id is non-numeric
    user = manager.get_user_by_id("1'; DROP TABLE users; --")
    
    # Bug: Unhandled exception
    manager.parse_json_input("{'invalid': json}")
