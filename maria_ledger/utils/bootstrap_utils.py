"""
bootstrap_utils.py

Core utilities for bootstrapping tables into ledger control.
Can be used by both CLI and library API.
"""

import json
from typing import Dict, List, Optional, Tuple, Any

from maria_ledger.db.connection import get_connection
from maria_ledger.db.merkle_service import compute_and_store_merkle_root
from maria_ledger.utils.helpers import json_serial
from maria_ledger.utils.schema import detect_table_schema, filter_columns
from maria_ledger.utils.triggers import generate_all_triggers


def snapshot_table_data(
    conn,
    table_name: str,
    primary_key: str,
    columns: List[str],
) -> Tuple[int, List[Tuple]]:
    """
    Snapshot existing table data into the ledger.

    Returns:
        Tuple of (row_count, snapshot_data_list)
    """
    cursor = conn.cursor(dictionary=True)
    try:
        # Select only the columns we want to track
        select_cols = ", ".join(columns)
        cursor.execute(f"SELECT {select_cols} FROM {table_name}")
        rows = cursor.fetchall()

        if not rows:
            return 0, []

        snapshot_data = []
        for row in rows:
            record_id = str(row[primary_key])
            # Convert row to JSON payload (only selected columns)
            payload_dict = {col: row.get(col) for col in columns}
            payload_str = json.dumps(payload_dict, default=json_serial)
            snapshot_data.append((table_name, record_id, "INSERT", payload_str))

        return len(rows), snapshot_data

    finally:
        cursor.close()


def insert_snapshot_into_ledger(conn, snapshot_data: List[Tuple]) -> None:
    """Insert snapshot data into the ledger table."""
    if not snapshot_data:
        return

    cursor = conn.cursor()
    try:
        insert_sql = """
        INSERT INTO ledger (table_name, record_id, op_type, new_payload)
        VALUES (%s, %s, %s, %s)
        """
        cursor.executemany(insert_sql, snapshot_data)
        conn.commit()
    finally:
        cursor.close()


def create_triggers(conn, table_name: str, primary_key: str, columns: List[str]) -> None:
    """Create database triggers for a table."""
    cursor = conn.cursor()
    try:
        trigger_statements = generate_all_triggers(table_name, primary_key, columns)

        # Execute each trigger statement
        for statement in trigger_statements:
            clean_stmt = statement.strip()
            if clean_stmt:
                # Assume append_ledger_entry procedure already exists
                cursor.execute(clean_stmt)
        conn.commit()

    finally:
        cursor.close()


def bootstrap_table_core(
    table_name: str,
    fields: Optional[List[str]] = None,
    primary_key: Optional[str] = None,
    snapshot_existing: bool = True,
    create_checkpoint: bool = True,
) -> Dict[str, Any]:
    """
    Core function to bootstrap a table into ledger control.
    Used by both CLI and library API.

    Args:
        table_name: Name of the table.
        fields: Optional list of fields to track. If None, tracks all columns.
        primary_key: Optional primary key column name. If None, auto-detected.
        snapshot_existing: Whether to snapshot existing data.
        create_checkpoint: Whether to create initial Merkle root checkpoint.

    Returns:
        Dict with: success, merkle_root, records_snapshotted, error (if any).
    """
    result = {
        "success": False,
        "merkle_root": None,
        "records_snapshotted": 0,
        "primary_key": None,
        "columns_tracked": [],
        "error": None,
    }

    conn = None
    try:
        conn = get_connection()

        # Step 1: Detect schema
        schema = detect_table_schema(table_name, primary_key)
        result["primary_key"] = schema["primary_key"]

        # Step 2: Filter columns based on fields parameter
        if fields:
            columns_to_track = filter_columns(
                schema["column_names"],
                fields,
                primary_key=schema["primary_key"],
            )
        else:
            columns_to_track = schema["column_names"]
        result["columns_tracked"] = columns_to_track

        # Step 3: Snapshot existing data
        if snapshot_existing:
            row_count, snapshot_data = snapshot_table_data(
                conn, table_name, schema["primary_key"], columns_to_track
            )
            if snapshot_data:
                insert_snapshot_into_ledger(conn, snapshot_data)
                result["records_snapshotted"] = row_count

        # Step 4: Create triggers
        create_triggers(conn, table_name, schema["primary_key"], columns_to_track)

        # Step 5: Create initial Merkle checkpoint
        if create_checkpoint:
            merkle_root = compute_and_store_merkle_root(table_name)
            result["merkle_root"] = merkle_root

        result["success"] = True
        return result

    except Exception as e:
        if conn:
            conn.rollback()
        result["error"] = str(e)
        result["success"] = False
        return result

    finally:
        if conn:
            conn.close()
