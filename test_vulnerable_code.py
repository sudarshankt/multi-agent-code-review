import os
import sqlite3
import subprocess
import ast
import shlex
import bcrypt
from flask import Flask, request

app = Flask(__name__)

ALLOWED_COMMANDS = ['ls', 'whoami', 'date', 'pwd', 'cat', 'echo']

@app.route('/user/<user_id>')
def get_user(user_id):
    """Retrieve user data from the database by user ID.

    Uses a parameterized query to prevent SQL injection.

    Args:
        user_id: The user identifier from the URL.

    Returns:
        A tuple representing the user row, or None if not found.
    """
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

@app.route('/execute')
def execute_command():
    """Execute an allowed command from a predefined list safely.

    Uses subprocess.run with shell=False and shlex.split to avoid
    command injection. Only commands in ALLOWED_COMMANDS are permitted.

    Args:
        Expects a 'cmd' query parameter.

    Returns:
        A string containing the command's stdout, or an error message
        with the appropriate HTTP status code.
    """
    cmd = request.args.get('cmd', '')
    if not cmd:
        return "No command provided", 400
    parts = shlex.split(cmd)
    if not parts or parts[0] not in ALLOWED_COMMANDS:
        return f"Command not allowed: {parts[0] if parts else 'empty'}", 403
    try:
        result = subprocess.run(parts, capture_output=True, text=True, shell=False)
        output = result.stdout.strip()
        return f"Executed: {output}"
    except Exception as e:
        return f"Error executing command: {e}", 500

@app.route('/eval')
def eval_code():
    """Safely evaluate a Python literal expression from user input.

    Uses ast.literal_eval to avoid arbitrary code execution.

    Args:
        Expects a 'code' query parameter containing a literal expression.

    Returns:
        The string representation of the evaluated literal, or an error
        message if the expression is invalid.
    """
    code = request.args.get('code', '')
    if not code:
        return "No code provided", 400
    try:
        result = ast.literal_eval(code)
    except (ValueError, SyntaxError, MemoryError, RecursionError) as e:
        return f"Invalid expression: {e}", 400
    return str(result)

def weak_hash(password):
    """Hash a password securely using bcrypt.

    Generates a random salt and hashes the password with the bcrypt algorithm.

    Args:
        password: The plain-text password to hash.

    Returns:
        The resulting bcrypt hash as a string.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode(), salt)
    return hashed.decode()
