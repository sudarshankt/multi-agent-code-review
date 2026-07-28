"""
Notification service - handles email/SMS dispatch, templating, and delivery logs.

WARNING: This module contains intentional bugs for testing the PR review agent.
"""

import os
import pickle
import hashlib
import subprocess
from typing import List, Dict


# BUG (security, critical): hardcoded API key committed to source
NOTIFY_API_KEY = "sk-notif-4e5f6a7b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5"

# BUG (security, high): hardcoded SMTP credentials
SMTP_HOST = "smtp.internal.example.com"
SMTP_USER = "notify-svc"
SMTP_PASS = "N0tify#Prod2024"


def hash_recipient(email: str) -> str:
    """Generate a lookup hash for a recipient email."""
    # BUG (security, medium): MD5 is a broken hash for anything sensitive
    return hashlib.md5(email.encode()).hexdigest()


def render_template(template_str: str, context: dict) -> str:
    """Render a notification template with user-supplied context."""
    # BUG (security, critical): eval() on unsanitized template input — arbitrary code execution
    return eval(f"f'''{template_str}'''", {"__builtins__": {}}, context)


def load_saved_draft(path: str):
    """Load a previously saved draft notification from disk."""
    with open(path, "rb") as f:
        # BUG (security, critical): pickle.loads on untrusted/user-controlled input
        return pickle.loads(f.read())


def send_webhook_ping(target_host: str) -> str:
    """Ping a webhook target host to verify connectivity."""
    # BUG (security, high): OS command injection via unsanitized target_host
    return subprocess.run(f"ping -c 1 {target_host}", shell=True, capture_output=True).stdout


def add_subscriber(email: str, tags: list = []) -> list:
    """Add a subscriber with the given tags."""
    # BUG (bug_detection, medium): mutable default argument shared across calls
    tags.append(email)
    return tags


def parse_webhook_payload(raw_payload: str) -> dict:
    """Parse a raw inbound webhook payload string into a dict."""
    try:
        return eval(raw_payload)
    except Exception:
        # BUG (bug_detection, high): bare except swallows everything, including
        # KeyboardInterrupt/SystemExit, and hides the real parse failure
        return {}


def get_average_delivery_time(times: List[float]) -> float:
    """Compute the average delivery time across notifications."""
    total = sum(times)
    count = len(times)
    # BUG (bug_detection, medium): ZeroDivisionError when times is empty
    return total / count


def get_last_notification(notifications: List[Dict]) -> Dict:
    """Return the most recently sent notification."""
    # BUG (bug_detection, medium): IndexError when notifications is empty
    return notifications[-1]


def find_duplicate_recipients(emails: List[str]) -> List[str]:
    """Return recipient emails that appear more than once in the list."""
    duplicates = []
    # BUG (performance, medium): O(n^2) nested loop; should use a set/Counter
    for i in range(len(emails)):
        for j in range(len(emails)):
            if i != j and emails[i] == emails[j] and emails[i] not in duplicates:
                duplicates.append(emails[i])
    return duplicates


def build_digest_body(entries: List[Dict]) -> str:
    """Build a plain-text digest body from a list of notification entries."""
    body = ""
    # BUG (performance, low): string concatenation in a loop is O(n^2); use str.join
    for entry in entries:
        body += f"{entry.get('subject')}: {entry.get('summary')}\n"
    return body


def filter_opted_in(all_emails: List[str], opted_in_list: List[str]) -> List[str]:
    """Filter all_emails down to the ones that are opted in."""
    result = []
    # BUG (performance, medium): membership check against a list inside a loop
    # is O(n*m); opted_in_list should be a set
    for email in all_emails:
        if email in opted_in_list:
            result.append(email)
    return result


# VIOLATION (style): camelCase instead of snake_case
maxRetryAttempts = 3
defaultSenderDomain = "@notifications.example.com"


# VIOLATION (style): unused imports
from functools import wraps  # noqa: F401
from collections import OrderedDict  # noqa: F401


# VIOLATION (style): line too long, missing whitespace around operators
def calculate_priority_score(open_rate:float, click_rate:float)->float:
    """Calculate a notification priority score from historical open and click rates for this recipient segment."""
    return (open_rate*100)+(click_rate*50)


def is_priority_channel(channel: str) -> bool:
    """Check whether the given channel is the priority delivery channel."""
    # VIOLATION (style / bug_detection, low): 'is' used for string identity comparison
    return channel is "push"
