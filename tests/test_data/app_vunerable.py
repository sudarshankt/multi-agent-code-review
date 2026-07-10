import os
import sqlite3
import requests

# ❌ VULNERABILITY 1: Hardcoded Sensitive Information (CWE-798 / OWASP A07)
# Real API keys or passwords should never be committed to code.
STRIPE_API_KEY = "sk_live_51NzABC123456789xyzYOURSECRETAPIKEY"

def get_db_connection():
    return sqlite3.connect('users.db')

def get_user_profile(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # ❌ VULNERABILITY 2: SQL Injection (CWE-89 / OWASP A03)
    # Using string formatting instead of parameterized queries allows attackers to execute arbitrary SQL.
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    
    user = cursor.fetchone()
    conn.close()
    return user

def ping_host(user_input_ip):
    # ❌ VULNERABILITY 3: OS Command Injection (CWE-78 / OWASP A03)
    # Passing raw user input directly to os.system allows attackers to execute system-level commands.
    command = f"ping -c 1 {user_input_ip}"
    os.system(command)

if __name__ == "__main__":
    # Test execution
    user = get_user_profile("admin' OR '1'='1")  # SQLi test payload
    ping_host("8.8.8.8; cat /etc/passwd")        # Command Injection test payload