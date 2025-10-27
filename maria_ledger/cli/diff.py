import typer
from tabulate import tabulate
from maria_ledger.db.connection import get_connection
from maria_ledger.cli.reconstruct import reconstruct_table_state

def diff_table_command(
    table: str,
    from_tx: int = typer.Option(..., "--from-tx", help="Starting transaction order ID."),
    to_tx: int = typer.Option(..., "--to-tx", help="Ending transaction order ID.")
):
    """
    Compare table states between two transaction points in the ledger.
    """
    conn = get_connection()

    try:
        # Reconstruct state at the "from" and "to" points
        typer.echo(f"Reconstructing state for '{table}' at transaction {from_tx}...")
        snapshot_from, _ = reconstruct_table_state(conn, table, as_of_tx_order=from_tx)

        typer.echo(f"Reconstructing state for '{table}' at transaction {to_tx}...")
        snapshot_to, _ = reconstruct_table_state(conn, table, as_of_tx_order=to_tx)

    finally:
        conn.close()

    added, removed, modified = [], [], []
    all_ids = set(snapshot_from.keys()) | set(snapshot_to.keys())

    for id_ in sorted(list(all_ids)):
        in_from = id_ in snapshot_from
        in_to = id_ in snapshot_to
        
        if not in_from and in_to:
            added.append({"id": id_, "data": snapshot_to[id_]})
        elif in_from and not in_to:
            removed.append({"id": id_, "data": snapshot_from[id_]})
        elif in_from and in_to and snapshot_from[id_] != snapshot_to[id_]:
            modified.append({"id": id_, "from_data": snapshot_from[id_], "to_data": snapshot_to[id_]})

    typer.echo("\n--- Ledger Diff ---\n")
    typer.echo(f"+ Added: {len(added)}  ~ Modified: {len(modified)}  - Deleted: {len(removed)}\n")

    if added:
        typer.echo("--- Added ---")
        typer.echo(tabulate(added, headers="keys", tablefmt="psql"))
    if modified:
        typer.echo("\n--- Modified ---")
        typer.echo(tabulate(modified, headers="keys", tablefmt="psql"))
    if removed:
        typer.echo("\n--- Removed ---")
        typer.echo(tabulate(removed, headers="keys", tablefmt="psql"))
