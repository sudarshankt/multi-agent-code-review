# Clear security and style issues for testing

def login_user(username, password):
    """Vulnerable: SQL injection and no input validation."""
    import sqlite3
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute(query)
    return cursor.fetchone()


def process_data(data):
    """Vulnerable: eval allows arbitrary code execution."""
    result = eval(data)
    return result


def hash_password(pwd):
    """Vulnerable: MD5 is not secure for passwords."""
    import hashlib
    return hashlib.md5(pwd.encode()).hexdigest()


def read_config(filename):
    """Unused imports and bare except."""
    import json
    import os  
    import sys  
    
    try:
        with open(filename) as f:
            return json.load(f)
    except:
        return {}


def calculate(x,y):
    """Missing docstring and poor style."""
    return x+y
