import os
import sqlite3
from flask import Flask, request

app = Flask(__name__)

@app.route('/user/<user_id>')
def get_user(user_id):
    # SQL Injection vulnerability
    query = f"SELECT * FROM users WHERE id = {user_id}"
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute(query)
    return cursor.fetchone()

@app.route('/execute')
def execute_command():
    # Command injection vulnerability
    cmd = request.args.get('cmd')
    result = os.system(cmd)
    return f"Executed: {cmd}"

@app.route('/eval')
def eval_code():
    # Unsafe eval
    code = request.args.get('code')
    return str(eval(code))

def weak_hash(password):
    import hashlib
    # Weak hash - should use bcrypt/argon2
    return hashlib.md5(password.encode()).hexdigest()
