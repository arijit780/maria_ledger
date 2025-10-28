"""
reconstruct.py

Utility for reconstructing the state of a table from an immutable ledger
and computing a Merkle root of that reconstructed state.

Functions:
    - canonicalize_json
    - compute_row_hash
    - load_ledger_stream
    - apply_ops_to_state
    - build_merkle_root_from_state
    - write_state_to_csv
    - (helpers) merkle_root_bytes, empty_tree_root, db_stream_query
"""

import typer
import json
import hashlib
import csv
from rich.console import Console
from typing import List, Optional
from maria_ledger.crypto.merkle_tree import MerkleTree


# ============================================================
# === Canonicalization & Hashing Utilities ===================
# ============================================================

from datetime import datetime

def json_serial(obj):
    """Custom JSON serializer for objects not serializable by default json code, like datetime."""
    if isinstance(obj, datetime):
        # Use isoformat() to include microseconds for full precision.
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def canonicalize_json(obj):
    """Return deterministic JSON bytes with sorted keys and compact form."""
    # Use a custom default serializer to handle datetimes with full precision.
    # This ensures that hashes are consistent between reconstructed and live states.
    return json.dumps(obj, separators=(',', ':'), sort_keys=True, default=json_serial).encode('utf-8')


def compute_row_hash(record_id, payload_json):
    """Compute SHA-256 hash for a given record (id + canonicalized JSON)."""
    data = f"{record_id}|{canonicalize_json(payload_json).decode('utf-8')}"
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


# ============================================================
# === Database Stream Reader =================================
# ============================================================

def db_stream_query(conn, sql, params):
    """
    Generator that yields rows using a server-side cursor for streaming.
    Assumes a mysql-connector-python connection.
    """
    # Use a dictionary cursor to get rows as dicts
    with conn.cursor(dictionary=True, buffered=False) as cur:
        cur.execute(sql, params)
        for row in cur:
            yield (
                row["tx_order"],
                row["record_id"],
                row["op_type"],
                row["old_payload"],
                row["new_payload"]
            )


def load_ledger_stream(conn, table_name, filters: Optional[List[str]] = None):
    """Yield ledger entries ordered by tx_order for a given table (streaming)."""
    sql = (
        "SELECT tx_order, record_id, op_type, old_payload, new_payload "
        "FROM ledger WHERE table_name = %s"
    )
    params = [table_name]

    if filters:
        filter_clauses = []
        # This is a simple implementation for equality. It can be expanded
        # to support operators like '>', '<', 'LIKE'.
        for f in filters:
            if ":" not in f:
                raise ValueError(f"Invalid filter format: '{f}'. Expected 'key:value'.")
            key, value = f.split(":", 1)
            # Basic validation to prevent injection on column names
            if not key.replace("_", "").isalnum():
                raise ValueError(f"Invalid filter key: {key}")
            filter_clauses.append(f"{key} = %s")
            params.append(value)
        sql += " AND " + " AND ".join(filter_clauses)

    sql += " ORDER BY tx_order ASC"
    for row in db_stream_query(conn, sql, params):
        yield row


# ============================================================
# === State Reconstruction ===================================
# ============================================================

def _parse_payload(payload):
    """
    Recursively parse a JSON payload to convert timestamp strings to datetime objects.
    This ensures data types are consistent with live table reads.
    """
    if not payload:
        return None
    
    # If the payload from the DB is a string, parse it into a dictionary first.
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return payload # Return as-is if not valid JSON
    for key, value in payload.items():
        # Handle nested dictionaries/objects if they exist
        if isinstance(value, dict):
            payload[key] = _parse_payload(value)
        if isinstance(value, str):
            # Attempt to parse strings that look like timestamps
            if key in ('created_at', 'updated_at') or 'at' in key:
                try:
                    payload[key] = datetime.fromisoformat(value.replace(' ', 'T'))
                except (ValueError, TypeError):
                    pass  # Not a timestamp string, leave as is
    return payload

def apply_ops_to_state(ledger_stream):
    """
    Apply INSERT/UPDATE/DELETE operations sequentially to reconstruct state.

    Args:
        ledger_stream: iterable of ledger rows
    Returns:
        dict: record_id -> final JSON payload
    """
    state = {}
    for tx_order, record_id, op_type, old_payload, new_payload in ledger_stream:
        if op_type == 'INSERT':
            state[record_id] = _parse_payload(new_payload)
        elif op_type == 'UPDATE':
            state[record_id] = _parse_payload(new_payload)
        elif op_type == 'DELETE':
            state.pop(record_id, None)
        else:
            raise ValueError(f"Unknown op_type '{op_type}' at tx_order {tx_order}")
    return state


def build_merkle_root_from_state(state_dict):
    """
    Compute deterministic Merkle root from reconstructed state.

    Args:
        state_dict: dict of record_id -> payload
    Returns:
        str: hex Merkle root
    """
    hashes = []
    for record_id in sorted(state_dict.keys()):
        payload = state_dict[record_id]
        row_hash = compute_row_hash(record_id, payload)
        hashes.append(row_hash)

    # Use the centralized MerkleTree class
    tree = MerkleTree(hashes)
    return tree.get_root()


# ============================================================
# === Output Helpers =========================================
# ============================================================

def write_state_to_csv(state_dict, filepath):
    """
    Write reconstructed state to a CSV file for audit/debug.
    Each row: record_id, payload_json
    """
    with open(filepath, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["record_id", "payload"])
        for record_id, payload in sorted(state_dict.items()):
            writer.writerow([record_id, json.dumps(payload, ensure_ascii=False)])


# ============================================================
# === Example Usage (programmatic) ============================
# ============================================================

def reconstruct_table_state(conn, table_name, out_csv=None, filters: Optional[List[str]] = None):
    """
    High-level function to reconstruct table state and compute Merkle root.

    Returns:
        tuple: (state_dict, merkle_root_hex)
    """
    # Pass filters down to the stream loader
    ledger_stream = load_ledger_stream(conn, table_name, filters)
    state = apply_ops_to_state(ledger_stream)
    merkle_root = build_merkle_root_from_state(state)

    if out_csv:
        write_state_to_csv(state, out_csv)

    return state, merkle_root


# ============================================================
# === Example for Integration ================================
# ============================================================

console = Console()

def reconstruct_command(
    table_name: str = typer.Argument(..., help="The logical table name within the ledger."),
    out_csv: str = typer.Option(None, "--out-csv", help="Path to write the reconstructed state as a CSV file."),
    filters: Optional[List[str]] = typer.Option(None, "--filter", help="Filter by 'key:value'. Can be used multiple times.")
):
    """
    Reconstruct a table's state from the ledger and print its Merkle root.
    """
    from maria_ledger.db.connection import get_connection
    conn = get_connection()

    try:
        console.print(f"Reconstructing state for [bold cyan]{table_name}[/]...")
        state, merkle_root = reconstruct_table_state(conn, table_name, out_csv, filters)
        console.print(f"\n[green]Reconstruction Complete[/green]")
        console.print(f"  - Records in final state: {len(state)}")
        console.print(f"  - Merkle Root: [bold white]{merkle_root}[/bold white]")
        if out_csv:
            console.print(f"  - State written to: [yellow]{out_csv}[/yellow]")
    finally:
        conn.close()
