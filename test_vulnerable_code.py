import os
import sqlite3
import subprocess
import shlex
import bcrypt
from flask import Flask, request

app = Flask(__name__)

ALLOWED_COMMANDS = {"ls", "dir", "pwd", "date", "whoami", "echo"}

@app.route('/user/<user_id>')
def get_user(user_id):
    # Validate user_id is convertible to integer
    try:
        int_user_id = int(user_id)
    except ValueError:
        return 'Invalid user ID', 400
    # Safe parameterized query with validated integer
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (int_user_id,))
    return cursor.fetchone()

@app.route('/execute')
def execute_command():
    cmd = request.args.get('cmd')
    if cmd is None:
        return 'Missing cmd parameter', 400
    if not cmd.strip():
        return 'No command provided', 400
    parts = shlex.split(cmd)
    if not parts:
        return 'Empty command', 400
    program = parts[0]
    if program not in ALLOWED_COMMANDS:
        return f"Command '{program}' not allowed", 403
    # Run allowed command safely
    subprocess.run(parts, shell=False, timeout=5)
    return f"Executed: {cmd}"

@app.route('/eval')
def eval_code():
    # eval removed for security; return safe message
    code = request.args.get('code')
    return "eval is disabled for security reasons"

def weak_hash(password):
    if password is None:
        raise ValueError('password must not be None')
    # Use bcrypt strong hashing
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()