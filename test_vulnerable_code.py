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
    # SQL Injection vulnerability fixed: use parameterized query
    query = "SELECT * FROM users WHERE id = ?"
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute(query, (user_id,))
    return cursor.fetchone()

@app.route('/execute')
def execute_command():
    # Command injection vulnerability fixed: whitelist allowed commands and use subprocess.run
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
    # Unsafe eval replaced with safe ast.literal_eval
    code = request.args.get('code', '')
    try:
        value = ast.literal_eval(code)
        return str(value)
    except (ValueError, SyntaxError) as e:
        return f"Invalid expression: {e}"

def weak_hash(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
