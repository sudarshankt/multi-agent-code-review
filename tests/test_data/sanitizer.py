def strip_username(name: str) -> str:
    """Strip leading and trailing whitespace from the username.
    
    This function only trims whitespace; it does NOT escape characters
    or prevent SQL injection. Use parameterized queries for database interactions.
    """
    if not name:
        return ""
    return name.strip()
