"""Test file with intentional bugs for agent detection."""

import sqlite3
import pickle
import os
from typing import Any


# ========== SECURITY ISSUES ==========

def get_user_from_db(user_id: str, db_path: str = "users.db") -> dict[str, Any]:
    """SQL Injection vulnerability - direct string concatenation."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # BUG: SQL Injection vulnerability
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    cursor.execute(query)
    return cursor.fetchone()


def load_user_data(serialized_data: bytes) -> Any:
    """Unsafe pickle deserialization - arbitrary code execution risk."""
    # BUG: Security issue - pickle can execute arbitrary code
    return pickle.loads(serialized_data)


def process_api_request(user_input: str) -> str:
    """XSS vulnerability - no input sanitization."""
    # BUG: No HTML escaping - XSS vulnerability
    return f"<div>{user_input}</div>"


HARDCODED_SECRET = "sk_test_xxxxxxxxxxxxxxxxxxxx"  # BUG: Should not hardcode secrets
API_KEY = "AKIA_test_xxxxxxxxxxxxxxxxxxxxx"  # BUG: Should not hardcode API keys


# ========== BUG DETECTION ISSUES ==========

def calculate_total_price(items: list[dict]) -> float:
    """Logic bug - undefined variable."""
    total = 0
    for item in items:
        quantity = item["qty"]
        # BUG: 'price' variable not defined, should be item["price"]
        total += price * quantity
    return total


def process_data(data: list) -> int:
    """Off-by-one error."""
    # BUG: IndexError - range should be range(len(data)-1) or range(len(data))
    for i in range(len(data) + 1):
        result = data[i]
    return result


def divide_numbers(a: int, b: int) -> float:
    """Missing null check."""
    # BUG: No check for b == 0 - division by zero
    return a / b


# ========== STYLE ISSUES ==========

def x(a, b, c):
    """Poor naming - function and variable names."""
    xxx = a + b
    yyy = xxx * c
    return yyy


def VeryLongFunctionNameWithManyParametersButNotFollowingConvention(p1, p2, p3, p4, p5):  # noqa
    """Inconsistent naming conventions."""
    result = p1 + p2 + p3 + p4 + p5
    return result


class MyClass:
    """Missing docstring and poorly organized."""
    def __init__(self):
        self.x = 1
        self.y = 2
        self.z = 3

    def method1(self):
        return self.x + self.y

    def method2(self):
        return self.x * self.y

    def method3(self):
        return self.y * self.z


# ========== PERFORMANCE ISSUES ==========

def inefficient_search(items: list[int], target: int) -> bool:
    """O(n²) complexity - inefficient nested loop."""
    found = False
    # BUG: Performance - quadratic complexity
    for i in items:
        for j in items:
            if i == target and j == target:
                found = True
    return found


def slow_string_concat(strings: list[str]) -> str:
    """String concatenation in loop - O(n²) complexity."""
    result = ""
    # BUG: Performance - repeated string concatenation
    for s in strings:
        result = result + s + ", "
    return result


def recursive_fibonacci(n: int) -> int:
    """Exponential time complexity - extremely inefficient."""
    # BUG: Performance - O(2^n) complexity without memoization
    if n <= 1:
        return n
    return recursive_fibonacci(n - 1) + recursive_fibonacci(n - 2)


def load_all_files_in_memory(directory: str) -> list[str]:
    """Memory inefficiency - loading everything at once."""
    files = []
    # BUG: Performance - loads all files at once, no streaming
    for filename in os.listdir(directory):
        with open(os.path.join(directory, filename), 'r') as f:
            files.append(f.read())
    return files


# ========== COMBINED ISSUES ==========

def process_user_payment(user_id: str, amount: str, payment_method: dict) -> bool:
    """Multiple issues combined."""
    # BUG: Security - SQL injection
    query = f"SELECT balance FROM users WHERE id={user_id}"
    
    # BUG: Type mismatch - amount is string but used in math
    total = float(amount) * 1.1
    
    # BUG: Unsafe data handling
    serialized = pickle.dumps(payment_method)
    
    # BUG: Logic - no error handling
    conn = sqlite3.connect("payments.db")
    cursor = conn.cursor()
    # BUG: Another SQL injection
    update_query = f"UPDATE users SET balance = balance - {amount} WHERE id = '{user_id}'"
    cursor.execute(update_query)
    
    return True


if __name__ == "__main__":
    # BUG: Unused variable
    test_data = [1, 2, 3, 4, 5]
    
    # This would crash at runtime
    # result = divide_numbers(10, 0)
    
    # This would cause an error
    # total = calculate_total_price([{"qty": 2}])
    
    print("Test file loaded - contains intentional bugs for agent detection")
