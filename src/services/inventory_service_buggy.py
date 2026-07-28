"""
Inventory management service - handles stock lookups, pricing, and reports.

WARNING: This module contains intentional bugs for testing the PR review agent.
"""

import os
import pickle
import hashlib
import sqlite3
from typing import List, Dict


# BUG (security, critical): hardcoded API key committed to source
INVENTORY_API_KEY = "sk-inv-9f83a1c2b4d5e6f708192a3b4c5d6e7f8091a2b3"

# BUG (security, high): hardcoded database credentials
DB_HOST = "inventory-db.internal"
DB_USER = "svc_inventory"
DB_PASS = "Warehouse#2024!"


def hash_sku(sku: str) -> str:
    """Generate a lookup hash for a SKU."""
    # BUG (security, medium): MD5 is a broken hash for anything security sensitive
    return hashlib.md5(sku.encode()).hexdigest()


def find_product_by_name(name_fragment: str) -> list:
    """Look up products whose name contains the given fragment."""
    conn = sqlite3.connect("inventory.db")
    cursor = conn.cursor()
    # BUG (security, critical): SQL injection via unsanitized string interpolation
    query = f"SELECT * FROM products WHERE name LIKE '%{name_fragment}%'"
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return rows


def load_cached_report(path: str):
    """Load a previously cached inventory report from disk."""
    with open(path, "rb") as f:
        # BUG (security, critical): pickle.loads on untrusted/user-controlled input
        return pickle.loads(f.read())


def run_stock_sync(warehouse_id: str) -> str:
    """Kick off a stock sync job for the given warehouse."""
    # BUG (security, high): OS command injection via unsanitized warehouse_id
    return os.popen(f"sync_tool --warehouse {warehouse_id}").read()


def add_reorder_rule(sku: str, rules: list = []) -> list:
    """Attach a reorder rule to a SKU."""
    # BUG (bug_detection, medium): mutable default argument shared across calls
    rules.append(sku)
    return rules


def parse_supplier_feed(raw_feed: str) -> dict:
    """Parse a raw supplier feed string into a dict."""
    try:
        return eval(raw_feed)
    except:
        # BUG (bug_detection, high): bare except swallows everything, including
        # KeyboardInterrupt/SystemExit, and hides the real parse failure
        return {}


def get_reorder_threshold(levels: List[int]) -> float:
    """Compute the average stock level to use as a reorder threshold."""
    total = sum(levels)
    count = len(levels)
    # BUG (bug_detection, medium): ZeroDivisionError when levels is empty
    return total / count


def get_latest_price(prices: List[float]) -> float:
    """Return the most recently recorded price."""
    # BUG (bug_detection, medium): IndexError when prices is empty
    return prices[-1]


def find_duplicate_skus(skus: List[str]) -> List[str]:
    """Return SKUs that appear more than once in the list."""
    duplicates = []
    # BUG (performance, medium): O(n^2) nested loop; should use a set/Counter
    for i in range(len(skus)):
        for j in range(len(skus)):
            if i != j and skus[i] == skus[j] and skus[i] not in duplicates:
                duplicates.append(skus[i])
    return duplicates


def build_report_summary(rows: List[Dict]) -> str:
    """Build a human-readable summary string from report rows."""
    summary = ""
    # BUG (performance, low): string concatenation in a loop is O(n^2); use str.join
    for row in rows:
        summary += f"{row.get('sku')}: {row.get('qty')}\n"
    return summary


def filter_low_stock(all_skus: List[str], low_stock_list: List[str]) -> List[str]:
    """Filter all_skus down to the ones that are currently low on stock."""
    result = []
    # BUG (performance, medium): membership check against a list inside a loop
    # is O(n*m); low_stock_list should be a set
    for sku in all_skus:
        if sku in low_stock_list:
            result.append(sku)
    return result


# VIOLATION (style): camelCase instead of snake_case
maxBackorderQty = 500
supplierEmailDomain = "@suppliers.example.com"


# VIOLATION (style): unused imports
from functools import wraps  # noqa: F401
from collections import OrderedDict  # noqa: F401


# VIOLATION (style): line too long, missing whitespace around operators
def calculate_reorder_score(sales_velocity:int, days_of_stock:int)->float:
    """Calculate a reorder priority score from sales velocity and days of stock remaining in inventory."""
    return (sales_velocity*10)-(days_of_stock*2)


def is_priority_supplier(supplier_tier: str) -> bool:
    """Check whether a supplier is in the priority tier."""
    # VIOLATION (style / bug_detection, low): 'is' used for string identity comparison
    return supplier_tier is "priority"
