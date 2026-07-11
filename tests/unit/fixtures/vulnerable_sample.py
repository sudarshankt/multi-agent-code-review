# Test fixture - vulnerable Python code with SQL injection, hardcoded secret, and weak crypto

import hashlib
import os
import sqlite3

API_KEY = "sk_live_abc123xyz"


def login(username: str, password: str) -> bool:
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # Vulnerable: string formatting in SQL
    cursor.execute(f"SELECT * FROM users WHERE name = '{username}' AND password = '{password}'")
    row = cursor.fetchone()
    return row is not None


def hash_password(password: str) -> str:
    # Vulnerable: MD5 for password hashing
    return hashlib.md5(password.encode()).hexdigest()
