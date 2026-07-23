import os
import sqlite3
import subprocess
import html
import hashlib
from flask import Flask, request, Response

app = Flask(__name__)

@app.route('/user/<user_id>')
def get_user(user_id):
    # Fixed SQL Injection: use parameterized query
    query = "SELECT * FROM users WHERE id = ?"
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute(query, (user_id,))
    return cursor.fetchone()

@app.route('/execute')
def execute_command():
    # Fixed command injection and XSS: use safe echo with subprocess, escape output
    cmd = request.args.get('cmd', '')
    # Use a safe command (echo) that does not allow arbitrary execution
    result = subprocess.run(['echo', cmd], capture_output=True, text=True, shell=False)
    output = html.escape(result.stdout.strip()) if result.stdout else ''
    return Response(f"Executed: {output}", mimetype='text/plain')

@app.route('/eval')
def eval_code():
    # Unsafe eval removed; code execution disabled
    return Response("eval is not permitted", mimetype='text/plain')

def weak_hash(password):
    # Replaced MD5 with scrypt, a strong KDF suitable for password hashing
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + ':' + dk.hex()
