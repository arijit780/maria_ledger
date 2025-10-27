"""
verify_state.py

Utility for verifying the current state of a table against the
reconstructed state from the immutable ledger.
"""
from maria_ledger.crypto.merkle_tree import MerkleTree

import typer
from rich.console import Console

from maria_ledger.db.connection import get_connection
from maria_ledger.cli.reconstruct import (
    reconstruct_table_state,
    build_merkle_root_from_state,
    compute_row_hash,
    db_stream_query
)

console = Console()


def load_current_state_stream(conn, table_name):
    """
    Generator that yields rows from the current state of a table.
    Assumes the table has a primary key column named 'id'.
    """
    # Assuming 'id' is the primary key and other columns are the payload.
    # This needs to be adapted if the schema is different.
    sql = f"SELECT * FROM {table_name} ORDER BY id"
    # Use a dictionary cursor and unbuffered to stream results
    with conn.cursor(dictionary=True, buffered=False) as cur:
        cur.execute(sql)
        for row in cur:
            record_id = str(row['id'])
            # Exclude the 'id' from the payload for hashing
            payload = {k: v for k, v in row.items() if k != 'id'}
            yield record_id, payload


def get_merkle_root_of_current_state(conn, table_name):
    """
    Computes the Merkle root of the current state of a given table.
    """
    # Stream hashes directly into the Merkle tree builder to save memory.
    hashes = [
        compute_row_hash(record_id, payload)
        for record_id, payload in load_current_state_stream(conn, table_name)
    ]
    return MerkleTree(hashes).get_root()


def find_discrepancies(reconstructed_state: dict, live_state_stream):
    """
    Compares reconstructed state with live state to find discrepancies using a
    memory-efficient streaming approach.
    """
    issues = []
    # Create sorted iterators for both sources
    recon_iter = iter(sorted(reconstructed_state.items()))
    live_iter = live_state_stream  # Assumes live stream is already sorted by ID

    try:
        recon_id, recon_payload = next(recon_iter)
    except StopIteration:
        recon_id = None
    try:
        live_id, live_payload = next(live_iter)
    except StopIteration:
        live_id = None

    while recon_id is not None or live_id is not None:
        if recon_id is not None and (live_id is None or recon_id < live_id):
            issues.append(f"MISSING in live table: ID {recon_id}")
            try:
                recon_id, recon_payload = next(recon_iter)
            except StopIteration:
                recon_id = None
        elif live_id is not None and (recon_id is None or live_id < recon_id):
            issues.append(f"EXTRA in live table (not in ledger): ID {live_id}")
            try:
                live_id, live_payload = next(live_iter)
            except StopIteration:
                live_id = None
        else:  # Both are not None and IDs match
            recon_hash = compute_row_hash(recon_id, recon_payload)
            live_hash = compute_row_hash(live_id, live_payload)
            if recon_hash != live_hash:
                issues.append(f"HASH MISMATCH for ID {live_id}")
            try:
                recon_id, recon_payload = next(recon_iter)
                live_id, live_payload = next(live_iter)
            except StopIteration:
                recon_id, live_id = None, None

    return issues


def verify_state_command(
    table_name: str = typer.Argument(..., help="The name of the live table to verify (e.g., 'customers')"),
    as_of_tx_order: int = typer.Option(None, help="Verify state as of a specific ledger transaction order."),
):
    """
    Verify a table's current state against the immutable ledger.
    """
    console.print(f"Verifying state of table [bold cyan]{table_name}[/]...")
    conn = get_connection()

    try:
        # 1. Reconstruct state from the ledger
        console.print("Reconstructing state from ledger...")
        reconstructed_state, reconstructed_root = reconstruct_table_state(conn, table_name, as_of_tx_order)
        console.print(f"  [green]✓[/green] Reconstructed Merkle root: [bold]{reconstructed_root}[/]")

        # 2. Compute Merkle root from the live table
        console.print(f"Computing Merkle root from live table '{table_name}'...")
        live_root = get_merkle_root_of_current_state(conn, table_name)
        console.print(f"  [green]✓[/green] Live table Merkle root: [bold]{live_root}[/]")

        # 3. Compare roots
        if reconstructed_root == live_root:
            console.print("\n[bold green]✅ SUCCESS: Live table state matches the ledger.[/bold green]")
        else:
            console.print("\n[bold red]❌ FAILURE: State mismatch detected![/bold red]")
            console.print("Finding discrepancies...")
            discrepancies = find_discrepancies(reconstructed_state, load_current_state_stream(conn, table_name))
            for issue in discrepancies:
                console.print(f"  - [yellow]{issue}[/yellow]")
            raise typer.Exit(code=1)

    finally:
        conn.close()
