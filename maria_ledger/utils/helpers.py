"""
helpers.py

Shared utility functions used across the CLI and other modules.
"""
import json
import decimal
from datetime import datetime, date
from typing import List, Optional, Tuple


def json_serial(obj):
    """Custom JSON serializer for objects not serializable by default json code, like datetime, Decimal."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        # Convert Decimal to float for JSON serialization
        # This preserves numeric value while making it JSON-compatible
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def canonicalize_json(obj):
    """Return deterministic JSON bytes with sorted keys and compact form."""
    return json.dumps(obj, separators=(',', ':'), sort_keys=True, default=json_serial).encode('utf-8')


def parse_filters(filters: Optional[List[str]]) -> Tuple[str, list]:
    """
    Parses a list of 'key:value' strings into an SQL WHERE clause and parameters.
    Returns a tuple of (sql_clause, params_list).
    """
    if not filters:
        return "", []

    filter_clauses = []
    params = []
    for f in filters:
        if ":" not in f:
            raise ValueError(f"Invalid filter format: '{f}'. Expected 'key:value'.")
        key, value = f.split(":", 1)
        # Basic validation to prevent injection on column names
        if not key.replace("_", "").isalnum():
            raise ValueError(f"Invalid filter key: {key}")
        filter_clauses.append(f"{key} = %s")
        params.append(value)

    return " AND " + " AND ".join(filter_clauses), params