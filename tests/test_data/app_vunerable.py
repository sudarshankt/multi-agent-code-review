import os
import sqlite3
import requests
import hashlib
import pickle

# ❌ VULNERABILITY 1: Hardcoded Sensitive Information (CWE-798 / OWASP A07)
# Real API keys or passwords should never be committed to code.
STRIPE_API_KEY = "sk_live_51NzABC123456789xyzYOURSECRETAPIKEY"

def get_db_connection():
    return sqlite3.connect('users.db')

def get_user_profile(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # ✅ Fixed: Use parameterized query to prevent SQL injection
    query = "SELECT * FROM users WHERE username = ?"
    cursor.execute(query, (username,))
    
    user = cursor.fetchone()
    conn.close()
    return user

# ❌ VULNERABILITY 4: Use of a Broken or Risky Cryptographic Algorithm (CWE-327 / OWASP A02)
# MD5 is cryptographically broken and prone to collision attacks. It should never be used for password hashing.
def hash_user_password(plain_password):
    hasher = hashlib.md5()
    hasher.update(plain_password.encode('utf-8'))
    return hasher.hexdigest()

# ❌ VULNERABILITY 5: Improper Limitation of a Pathname to a Restricted Directory (CWE-22 / OWASP A01)
# Directly joining user input with paths allows directory traversal (e.g., inputting '../../etc/passwd').
def read_user_file(user_provided_filename):
    base_dir = "/var/www/uploads/"
    filepath = os.path.join(base_dir, user_provided_filename)
    with open(filepath, "r") as f:
        return f.read()

# ❌ VULNERABILITY 6: Deserialization of Untrusted Data (CWE-502 / OWASP A08)
# The pickle module is highly unsafe for parsing data from untrusted sources; it can lead to Remote Code Execution (RCE).
def load_session_data(serialized_cookie_data):
    # This will execute arbitrary code if the payload is malicious
    return pickle.loads(serialized_cookie_data)

def ping_host(user_input_ip):
    # ❌ VULNERABILITY 3: OS Command Injection (CWE-78 / OWASP A03)
    # Passing raw user input directly to os.system allows attackers to execute system-level commands.
    command = f"ping -c 1 {user_input_ip}"
    os.system(command)
    # Attempting to fix OS Command Injection using subprocess
    import subprocess
    # Still vulnerable because shell=True executes commands via the system shell!
    subprocess.run(f"ping -c 1 {user_input_ip}", shell=True)

if __name__ == "__main__":
    # Test executions (benign demonstrations)
    print("Hashing password using MD5:", hash_user_password("super_secure_123"))
    
    # These would fail or trigger exploits in production:
    get_user_profile("admin' OR '1'='1")
    ping_host("8.8.8.8; cat /etc/passwd")
    # read_user_file("../../../etc/passwd")
