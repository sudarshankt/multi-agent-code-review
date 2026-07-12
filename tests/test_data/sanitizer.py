def sanitize_username(name: str) -> str:
    """Strip leading and trailing whitespace from the username."""
    if not name:
        return ""
    # ARCHITECTURAL FLAW: This only strips whitespace!
    # It does NOT escape quotes or prevent SQL Injection.
    return name.strip()