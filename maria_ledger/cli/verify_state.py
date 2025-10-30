"""
verify_state.py

Utility for verifying the current state of a table against the
reconstructed state from the immutable ledger.
"""
from maria_ledger.crypto.merkle_tree import MerkleTree

import typer
from rich.console import Console
from typing import List, Optional

from maria_ledger.db.connection import get_connection
from maria_ledger.cli.reconstruct import (
    reconstruct_table_state,
    build_merkle_root_from_state,
    compute_row_hash, _parse_payload,
    db_stream_query,
    parse_filters
)

console = Console()


def load_current_state_stream(conn, table_name, filters: Optional[List[str]] = None):
    """
    Generator that yields rows from the current state of a table.
    Assumes the table has a primary key column named 'id'.
    """
    # Assuming 'id' is the primary key and other columns are the payload.
    # This needs to be adapted if the schema is different.
    sql = f"SELECT * FROM {table_name}"
    params = []
    filter_sql, filter_params = parse_filters(filters)
    sql += " WHERE 1=1" + filter_sql # Start with WHERE 1=1 to simplify appending
    params.extend(filter_params)
    sql += " ORDER BY id"

    # Use a dictionary cursor and unbuffered to stream results
    with conn.cursor(dictionary=True, buffered=False) as cur:
        cur.execute(sql, params)
        for row in cur:
            record_id = str(row['id'])
            # Exclude the 'id' from the payload for hashing
            payload = {k: v for k, v in row.items() if k != 'id'}
            # Ensure datetime objects are handled consistently with reconstruction
            yield record_id, _parse_payload(payload)


def get_merkle_root_of_current_state(conn, table_name, filters: Optional[List[str]] = None, fields_to_hash: Optional[List[str]] = None):
    """
    Computes the Merkle root of the current state of a given table.
    """
    # Stream hashes directly into the Merkle tree builder to save memory.
    hashes = [
        compute_row_hash(record_id, payload, fields_to_hash=fields_to_hash)
        for record_id, payload in load_current_state_stream(conn, table_name, filters)
    ]
    return MerkleTree(hashes).get_root()


def find_discrepancies(reconstructed_state: dict, live_state_stream, fields_to_hash: Optional[List[str]] = None):
    """
    Compares reconstructed state with live state to find discrepancies using a
    memory-efficient streaming approach.
    """
    issues = []
    # Create sorted iterators for both sources
    # Sort by integer value of the key to ensure correct numerical order.
    recon_iter = iter(sorted(reconstructed_state.items(), key=lambda item: int(item[0])))
    live_iter = live_state_stream  # Assumes live stream is already sorted by ID

    # Helper functions to safely get the next item from an iterator
    def get_next(it):
        try:
            return next(it)
        except StopIteration:
            return None, None

    recon_id, recon_payload = get_next(recon_iter)
    live_id, live_payload = get_next(live_iter)

    while recon_id is not None or live_id is not None:
        # Compare IDs as integers for correct numerical comparison.
        recon_id_int = int(recon_id) if recon_id is not None else None
        live_id_int = int(live_id) if live_id is not None else None

        # Case 1: Reconstructed ID is smaller or live stream is exhausted.
        # This means the record is in the ledger but missing from the live table.
        if recon_id_int is not None and (live_id_int is None or recon_id_int < live_id_int):
            issues.append(f"MISSING in live table: ID {recon_id}")
            recon_id, recon_payload = get_next(recon_iter)

        # Case 2: Live ID is smaller or reconstructed stream is exhausted.
        # This means the record is in the live table but not in the ledger history.
        elif live_id_int is not None and (recon_id_int is None or live_id_int < recon_id_int):
            issues.append(f"EXTRA in live table (not in ledger): ID {live_id}")
            live_id, live_payload = get_next(live_iter)

        # Case 3: IDs match. Now we compare the content.
        elif recon_id_int == live_id_int:
            recon_hash = compute_row_hash(recon_id, recon_payload, fields_to_hash=fields_to_hash)
            live_hash = compute_row_hash(live_id, live_payload, fields_to_hash=fields_to_hash)
            if recon_hash != live_hash:
                issues.append(f"HASH MISMATCH for ID {live_id}")
            
            # Advance both iterators
            recon_id, recon_payload = get_next(recon_iter)
            live_id, live_payload = get_next(live_iter)

    return issues


def verify_state_command(
    table_name: str = typer.Argument(..., help="The name of the live table to verify (e.g., 'customers')"),
    filters: Optional[List[str]] = typer.Option(None, "--filter", help="Filter by 'key:value'. Can be used multiple times.")
):
    """
    Verify a table's current state against the immutable ledger.
    """
    console.print(f"Verifying state of table [bold cyan]{table_name}[/]...")
    conn = get_connection()

    # Define the fields that are critical for integrity verification.
    # Timestamps like 'created_at' and 'updated_at' are intentionally excluded.
    fields_to_hash = ['name', 'email']
    console.print(f"Verifying against critical fields: [bold yellow]id, {', '.join(fields_to_hash)}[/bold yellow]")

    try:
        # 1. Reconstruct state from the ledger
        console.print("Reconstructing state from ledger...")
        reconstructed_state, reconstructed_root = reconstruct_table_state(conn, table_name, filters=filters, fields_to_hash=fields_to_hash)
        console.print(f"  [green]✓[/green] Reconstructed Merkle root: [bold]{reconstructed_root}[/]")

        # 2. Compute Merkle root from the live table
        console.print(f"Computing Merkle root from live table '{table_name}'...")
        live_root = get_merkle_root_of_current_state(conn, table_name, filters=filters, fields_to_hash=fields_to_hash)
        console.print(f"  [green]✓[/green] Live table Merkle root: [bold]{live_root}[/]")

        # 3. Compare roots
        if reconstructed_root == live_root:
            console.print("\n[bold green]✅ SUCCESS: Live table state matches the ledger based on critical fields.[/bold green]")
        else:
            console.print("\n[bold red]❌ FAILURE: State mismatch detected![/bold red]")
            console.print("Finding discrepancies...")
            live_stream = load_current_state_stream(conn, table_name, filters=filters)
            try:
                discrepancies = find_discrepancies(reconstructed_state, live_stream, fields_to_hash=fields_to_hash)
                for issue in discrepancies:
                    console.print(f"  - [yellow]{issue}[/yellow]")
                raise typer.Exit(code=1)
            finally:
                # This is crucial: ensure the generator is fully consumed
                # to prevent the "Unread result found" error with unbuffered cursors.
                from collections import deque
                deque(live_stream, maxlen=0)

    finally:
        conn.close()
