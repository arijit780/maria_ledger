"""
schema.py

Utilities for detecting table schema and primary keys from MariaDB.
"""

from typing import Dict, List, Optional
from maria_ledger.db.connection import get_connection


def get_table_columns(conn, table_name: str) -> List[Dict[str, any]]:
    """
    Get all columns for a table from information_schema.

    Returns:
        List of column dicts with: column_name, data_type, is_nullable
    """
    cursor = conn.cursor(dictionary=True)
    try:
        # Get database name from connection
        cursor.execute("SELECT DATABASE() as db_name")
        db_result = cursor.fetchone()
        db_name = db_result["db_name"] if db_result else None
        if not db_name:
            raise ValueError("Could not determine current database")

        cursor.execute(
            """
            SELECT column_name, data_type, is_nullable, column_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (db_name, table_name),
        )
        return cursor.fetchall()

    finally:
        cursor.close()


def get_primary_key(conn, table_name: str) -> Optional[str]:
    """
    Get the primary key column name for a table.

    Returns:
        Primary key column name, or None if no primary key exists.
    """
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT DATABASE() as db_name")
        db_result = cursor.fetchone()
        db_name = db_result["db_name"] if db_result else None
        if not db_name:
            raise ValueError("Could not determine current database")

        cursor.execute(
            """
            SELECT k.column_name
            FROM information_schema.table_constraints t
            JOIN information_schema.key_column_usage k
                ON t.constraint_name = k.constraint_name
                AND t.table_schema = k.table_schema
                AND t.table_name = k.table_name
            WHERE t.constraint_type = 'PRIMARY KEY'
                AND t.table_schema = %s
                AND t.table_name = %s
            ORDER BY k.ordinal_position
            LIMIT 1
            """,
            (db_name, table_name),
        )
        result = cursor.fetchone()
        return result["column_name"] if result else None

    finally:
        cursor.close()


def detect_table_schema(table_name: str, primary_key: Optional[str] = None) -> Dict[str, any]:
    """
    Detect table schema including columns and primary key.

    Args:
        table_name: Name of the table.
        primary_key: Optional primary key column name. If not provided, auto-detected.

    Returns:
        Dict with: columns (list), primary_key (str), column_names (list)

    Raises:
        ValueError: If table doesn't exist or has no primary key.
    """
    conn = get_connection()
    try:
        columns = get_table_columns(conn, table_name)
        if not columns:
            raise ValueError(f"Table '{table_name}' does not exist or has no columns")

        # Auto-detect primary key if not provided
        if not primary_key:
            primary_key = get_primary_key(conn, table_name)
            if not primary_key:
                raise ValueError(
                    f"Table '{table_name}' has no primary key. "
                    "Please specify the unique identifier column using the 'primary_key' parameter."
                )

        # Verify primary key exists in columns
        column_names = [col["column_name"] for col in columns]
        if primary_key not in column_names:
            raise ValueError(f"Specified primary key '{primary_key}' not found in table columns")

        return {
            "columns": columns,
            "primary_key": primary_key,
            "column_names": column_names,
        }

    finally:
        conn.close()


def filter_columns(
    column_names: List[str],
    fields: Optional[List[str]] = None,
    primary_key: Optional[str] = None,
) -> List[str]:
    """
    Filter column names based on fields list.
    Primary key is always included regardless of fields list.

    Args:
        column_names: All column names in the table.
        fields: Optional list of fields to include. If None, includes all.
        primary_key: Primary key column (always included).

    Returns:
        Filtered list of column names.
    """
    if fields is None:
        return column_names

    # Always include primary key first
    filtered = []
    if primary_key and primary_key in column_names:
        filtered.append(primary_key)

    # Add specified fields (excluding primary_key to avoid duplicates)
    for field in fields:
        if field in column_names and field not in filtered:
            filtered.append(field)

    return filtered
