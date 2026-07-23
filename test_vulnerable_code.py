import os
import sqlite3
import subprocess
import ast
import bcrypt
from flask import Flask, request

app = Flask(__name__)

ALLOWED_COMMANDS = {'ls', 'date', 'whoami', 'pwd', 'echo', 'cat'}

@app.route('/user/<user_id>')
def get_user(user_id):
    """Retrieve a user by ID from the database.

    Parameters:
        user_id (str): The user ID to look up.

    Returns:
        tuple or None: The user record if found, else None.

    Security:
        Uses parameterized query to prevent SQL injection.
    """
    with sqlite3.connect(':memory:') as db:
        cursor = db.cursor()
        query = "SELECT * FROM users WHERE id = ?"
        cursor.execute(query, (user_id,))
        return cursor.fetchone()

@app.route('/execute')
def execute_command():
    """Execute a predefined safe shell command.

    Parameters:
        cmd (str): The command name passed via query parameter 'cmd'.

    Returns:
        str: Execution output or error message.

    Security:
        Only whitelisted commands are allowed; uses subprocess.run with shell=False
        to prevent command injection.
    """
    cmd = request.args.get('cmd', '')
    if cmd not in ALLOWED_COMMANDS:
        return f"Command not allowed: {cmd}"
    try:
        result = subprocess.run([cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False, timeout=5)
        output = result.stdout if result.returncode == 0 else result.stderr
        return f"Executed: {cmd}\nOutput: {output}"
    except Exception as e:
        return f"Error executing command: {e}"

@app.route('/eval')
def eval_code():
    """Safely evaluate a literal Python expression.

    Parameters:
        code (str): The expression string passed via query parameter 'code'.

    Returns:
        str: The evaluated value or an error message.

    Security:
        Uses ast.literal_eval to prevent arbitrary code execution.
    """
    code = request.args.get('code', '')
    try:
        value = ast.literal_eval(code)
        return str(value)
    except (ValueError, SyntaxError) as e:
        return f"Invalid expression: {e}"

def weak_hash(password):
    """Hash a password using bcrypt.

    Parameters:
        password (str): The plaintext password to hash.

    Returns:
        str: The bcrypt hash as a string.

    Note:
        This function should only be used for strong, salted hashing.
        Ensure the password is not weak or commonly used.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
