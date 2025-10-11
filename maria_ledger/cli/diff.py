import typer
from tabulate import tabulate
from maria_ledger.db.connection import get_connection

def diff_table_command(table: str, from_: str = typer.Option(..., "--from", help="Start timestamp (YYYY-MM-DD)"),
                       to: str = typer.Option(..., "--to", help="End timestamp (YYYY-MM-DD)")):
    """
    Compare ledger table rows between two time snapshots.
    Works by selecting rows valid during each time period and diffing hashes.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Snapshot 1
    cursor.execute(f"""
        SELECT id, name, email, row_hash
        FROM {table}
        WHERE valid_from <= %s AND (valid_to IS NULL OR valid_to > %s)
    """, (from_, from_))
    snapshot_from = {row['id']: row for row in cursor.fetchall()}

    # Snapshot 2
    cursor.execute(f"""
        SELECT id, name, email, row_hash
        FROM {table}
        WHERE valid_from <= %s AND (valid_to IS NULL OR valid_to > %s)
    """, (to, to))
    snapshot_to = {row['id']: row for row in cursor.fetchall()}

    cursor.close()
    conn.close()

    added, removed, modified = [], [], []

    for id_, row in snapshot_to.items():
        if id_ not in snapshot_from:
            added.append(row)
        elif row['row_hash'] != snapshot_from[id_]['row_hash']:
            modified.append({"id": id_, "old_hash": snapshot_from[id_]['row_hash'], "new_hash": row['row_hash']})

    for id_, row in snapshot_from.items():
        if id_ not in snapshot_to:
            removed.append(row)

    typer.echo("\n--- Ledger Diff ---\n")
    typer.echo(f"+ Added: {len(added)}  ~ Modified: {len(modified)}  - Deleted: {len(removed)}\n")

    if added:
        typer.echo(tabulate(added, headers="keys", tablefmt="psql"))
    if modified:
        typer.echo(tabulate(modified, headers="keys", tablefmt="psql"))
    if removed:
        typer.echo(tabulate(removed, headers="keys", tablefmt="psql"))
