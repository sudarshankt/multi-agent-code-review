import os
import sqlite3
import subprocess
import ast
import bcrypt
from flask import Flask, request

app = Flask(__name__)

@app.route('/user/<user_id>')
def get_user(user_id):
    """Fetch user data by user_id from in-memory database."""
    # SQL Injection fixed with parameterized query
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

@app.route('/execute')
def execute_command():
    """Execute an arbitrary shell command passed via 'cmd' query parameter."""
    cmd = request.args.get('cmd', '')
    allowed_commands = {'date', 'whoami', 'ls', 'pwd'}
    if cmd not in allowed_commands:
        return "Command not allowed"
    result = subprocess.run([cmd], capture_output=True, text=True, shell=False)
    if result.returncode == 0:
        return result.stdout
    else:
        return f"Command failed: {result.stderr}"

@app.route('/eval')
def eval_code():
    """Evaluate and return the result of Python code passed via 'code' query parameter."""
    code = request.args.get('code')
    try:
        result = ast.literal_eval(code)
    except (ValueError, SyntaxError):
        return "Invalid input for evaluation"
    return str(result)

def weak_hash(password):
    """Hash a password using bcrypt and return the resulting hash string."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode(), salt)
    return hashed.decode()
