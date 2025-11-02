"""
triggers.py

Utilities for generating dynamic SQL triggers for ledger tracking.
"""

from typing import List


def build_json_object_sql(columns: List[str], row_prefix: str = "NEW") -> str:
    """
    Build SQL JSON_OBJECT clause for a list of columns.

    Args:
        columns: List of column names.
        row_prefix: "NEW" or "OLD" for INSERT/UPDATE/DELETE contexts.

    Returns:
        SQL string like:
        JSON_OBJECT('col1', NEW.col1, 'col2', NEW.col2, ...)

    Note:
        For string columns, we convert to ensure utf8mb4_general_ci collation.
        Numeric and other types are included as-is.
    """
    pairs = []
    for col in columns:
        # For simplicity and consistency, convert all columns to utf8mb4 text
        pairs.append(f"'{col}', CONVERT({row_prefix}.{col} USING utf8mb4) COLLATE utf8mb4_general_ci")

    return "JSON_OBJECT(" + ", ".join(pairs) + ")"


def generate_trigger_sql(
    table_name: str,
    primary_key: str,
    columns: List[str],
    trigger_name_suffix: str = "",
) -> str:
    """
    Generate SQL for a single trigger (INSERT, UPDATE, or DELETE).

    Args:
        table_name: Table name.
        primary_key: Primary key column name.
        columns: List of columns to track in the ledger.
        trigger_name_suffix: "insert", "update", or "delete".

    Returns:
        SQL CREATE TRIGGER statement (without DELIMITER, ready to execute).
    """
    trigger_name = f"{table_name}_after_{trigger_name_suffix}"

    # Build JSON payloads
    new_json = build_json_object_sql(columns, "NEW")
    old_json = build_json_object_sql(columns, "OLD") if trigger_name_suffix in ("update", "delete") else None

    if trigger_name_suffix == "insert":
        return f"""
DROP TRIGGER IF EXISTS {trigger_name};
CREATE TRIGGER {trigger_name}
AFTER INSERT ON {table_name} FOR EACH ROW
BEGIN
    CALL append_ledger_entry(
        '{table_name}',
        CAST(NEW.{primary_key} AS CHAR),
        'INSERT',
        NULL,
        {new_json}
    );
END
""".strip()

    elif trigger_name_suffix == "update":
        return f"""
DROP TRIGGER IF EXISTS {trigger_name};
CREATE TRIGGER {trigger_name}
AFTER UPDATE ON {table_name} FOR EACH ROW
BEGIN
    CALL append_ledger_entry(
        '{table_name}',
        CAST(NEW.{primary_key} AS CHAR),
        'UPDATE',
        {old_json},
        {new_json}
    );
END
""".strip()

    elif trigger_name_suffix == "delete":
        return f"""
DROP TRIGGER IF EXISTS {trigger_name};
CREATE TRIGGER {trigger_name}
AFTER DELETE ON {table_name} FOR EACH ROW
BEGIN
    CALL append_ledger_entry(
        '{table_name}',
        CAST(OLD.{primary_key} AS CHAR),
        'DELETE',
        {old_json},
        NULL
    );
END
""".strip()

    else:
        raise ValueError(f"Invalid trigger_name_suffix: {trigger_name_suffix}")


def generate_all_triggers(
    table_name: str,
    primary_key: str,
    columns: List[str],
) -> List[str]:
    """
    Generate SQL for all three triggers (INSERT, UPDATE, DELETE).

    Returns:
        List of SQL statements (one for each trigger).
    """
    return [
        generate_trigger_sql(table_name, primary_key, columns, "insert"),
        generate_trigger_sql(table_name, primary_key, columns, "update"),
        generate_trigger_sql(table_name, primary_key, columns, "delete"),
    ]
