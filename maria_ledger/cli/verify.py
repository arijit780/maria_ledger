import typer
from maria_ledger.db.merkle_service import verify_table_with_merkle_root, compute_and_store_merkle_root
from maria_ledger.db.connection import get_connection

def verify_table_command(table: str):
    """
    Verify integrity of table by recomputing Merkle root and comparing
    against the latest entry in ledger_roots.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT root_hash FROM ledger_roots
        WHERE table_name=%s
        ORDER BY computed_at DESC
        LIMIT 1
    """, (table,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        typer.echo(f"[i] No Merkle root stored for table {table}. Computing now...")
        new_root = compute_and_store_merkle_root(table)
        typer.echo(f"[✓] Stored initial Merkle root: {new_root}")
        return

    latest_root = row["root_hash"]
    typer.echo(f"[•] Latest recorded root: {latest_root}")
    ok = verify_table_with_merkle_root(table, latest_root)
    typer.echo(f"[✓] Table {table} integrity OK" if ok else f"[✗] Integrity mismatch detected!")
