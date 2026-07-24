import ast
import sqlite3
import subprocess
import bcrypt
from flask import Flask, request

app = Flask(__name__)

@app.route('/user/<user_id>')
def get_user(user_id):
    # Fixed SQL Injection: parameterized query
    query = "SELECT * FROM users WHERE id = ?"
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute(query, (user_id,))
    return cursor.fetchone()

@app.route('/execute')
def execute_command():
    # Fixed Command Injection: strict allowlist and subprocess with shell=False
    ALLOWED_COMMANDS = {'ls', 'date', 'whoami'}
    cmd = request.args.get('cmd')
    if cmd not in ALLOWED_COMMANDS:
        return "Command not allowed"
    subprocess.run([cmd], capture_output=True, shell=False)
    return f"Executed: {cmd}"

@app.route('/eval')
def eval_code():
    # Fixed Code Injection: use ast.literal_eval instead of eval
    code = request.args.get('code')
    try:
        return str(ast.literal_eval(code))
    except (ValueError, SyntaxError) as e:
        return f"Invalid input: {e}"

def weak_hash(password):
    # Fixed Weak Hash: bcrypt with unique salt per password
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')