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
    # Fixed SQL Injection: use parameterized query
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

@app.route('/execute')
def execute_command():
    # Fixed command injection: use allowlist and subprocess.run with list
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
    # Fixed unsafe eval: use ast.literal_eval for safe evaluation
    code = request.args.get('code', '')
    if not code:
        return "No code provided", 400
    try:
        result = ast.literal_eval(code)
    except (ValueError, SyntaxError, MemoryError, RecursionError) as e:
        return f"Invalid expression: {e}", 400
    return str(result)

def weak_hash(password):
    import bcrypt
    # Fixed: use bcrypt with salt and work factor
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode(), salt)
    return hashed.decode()
