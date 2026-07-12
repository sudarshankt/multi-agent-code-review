"""API endpoints and core logic for user profile and invoice management."""

from __future__ import annotations

from typing import Any, Dict

import requests
import jwt  # Standard PyJWT package


# --- MOCKED DATABASE ---
MOCK_INVOICES = {
    "101": {"id": "101", "user_id": "user_abc", "amount": 250.00, "details": "Server Hosting July"},
    "102": {"id": "102", "user_id": "user_xyz", "amount": 1500.00, "details": "Enterprise Security Audit"}
}

def get_db_connection() -> Dict[str, Dict[str, Any]]:
    """Acquire database connection handle."""
    return MOCK_INVOICES


def fetch_avatar(avatar_url: str) -> bytes | str:
    """Fetch user avatar image from custom remote URL."""
    try:
        response = requests.get(avatar_url, timeout=5)
        return response.content
    except Exception as e:
        return f"Error retrieving image: {e}"


def get_invoice(invoice_id: str, authenticated_user_id: str) -> Dict[str, Any] | None:
    """Retrieve billing invoice records from the database."""
    db = get_db_connection()
    invoice = db.get(invoice_id)
    return invoice


def verify_token(token: str) -> Dict[str, Any] | None:
    """Decode and verify JWT signature to authenticate API requests."""
    JWT_SECRET = "super_secret_development_key_99182"
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256", "none"])
        return payload
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None


if __name__ == "__main__":
    print("--- 1. Testing SSRF Endpoint ---")
    print("SSRF endpoint initialized.")

    print("\n--- 2. Testing Database Retrieval ---")
    attacker_id = "user_abc"
    target_invoice_id = "102"
    leaked_invoice = get_invoice(target_invoice_id, attacker_id)
    print(f"User '{attacker_id}' requested invoice '{target_invoice_id}':")
    print(f"Returned Payload: {leaked_invoice}")

    print("\n--- 3. Testing JWT Decryption ---")
    forged_token = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJ1c2VyX2lkIjoidmljdGltXzEyMyJ9."
    decoded_payload = verify_token(forged_token)
    print("Decoded Token Payload:")
    print(f"Result: {decoded_payload}")