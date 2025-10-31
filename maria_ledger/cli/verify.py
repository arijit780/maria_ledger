"""
verify.py

Unified CLI command to verify table integrity with multiple verification modes.
"""

import typer
from rich.console import Console
from typing import List, Optional

from maria_ledger.db.connection import get_connection
from maria_ledger.db.merkle_service import (
    get_latest_merkle_root,
    compute_root_from_chain_hashes,
    compute_and_store_merkle_root,
)
from maria_ledger.crypto.signer import verify_merkle_root_signature
from maria_ledger.utils.config import get_config
from maria_ledger.cli.reconstruct import (
    reconstruct_table_state,
    build_merkle_root_from_state,
    _parse_payload,
    db_stream_query,
    parse_filters,
)
from maria_ledger.crypto.hash_utils import compute_record_hash

console = Console()


# ============================================================
# === Load Current Table State ===============================
# ============================================================

def load_current_state_stream(conn, table_name, filters: Optional[List[str]] = None):
    """
    Generator that yields rows from the current state of a table.
    Assumes the table has a primary key column named 'id'.
    """
    sql = f"SELECT * FROM {table_name}"
    params = []

    filter_sql, filter_params = parse_filters(filters)
    sql += " WHERE 1=1" + filter_sql
    params.extend(filter_params)
    sql += " ORDER BY id"

    with conn.cursor(dictionary=True, buffered=False) as cur:
        cur.execute(sql, params)
        for row in cur:
            record_id = str(row["id"])
            payload = {k: v for k, v in row.items() if k != "id"}
            yield record_id, _parse_payload(payload)


# ============================================================
# === Compute Merkle Root for Live Table =====================
# ============================================================

def get_merkle_root_of_current_state(
    conn,
    table_name,
    filters: Optional[List[str]] = None,
    fields_to_hash: Optional[List[str]] = None,
):
    """Computes the Merkle root of the current state of a given table."""
    from maria_ledger.crypto.merkle_tree import MerkleTree

    hashes = [
        compute_record_hash(record_id, payload, fields_to_hash=fields_to_hash)
        for record_id, payload in load_current_state_stream(conn, table_name, filters)
    ]
    return MerkleTree(hashes).get_root()


# ============================================================
# === Compare Ledger vs Live State ===========================
# ============================================================

def find_discrepancies(
    reconstructed_state: dict, live_state_stream, fields_to_hash: Optional[List[str]] = None
):
    """Compares reconstructed state with live state to find discrepancies."""
    issues = []

    recon_iter = iter(sorted(reconstructed_state.items(), key=lambda item: int(item[0])))
    live_iter = live_state_stream

    def get_next(it):
        try:
            return next(it)
        except StopIteration:
            return None, None

    recon_id, recon_payload = get_next(recon_iter)
    live_id, live_payload = get_next(live_iter)

    while recon_id is not None or live_id is not None:
        recon_id_int = int(recon_id) if recon_id is not None else None
        live_id_int = int(live_id) if live_id is not None else None

        if recon_id_int is not None and (live_id_int is None or recon_id_int < live_id_int):
            issues.append(f"MISSING in live table: ID {recon_id}")
            recon_id, recon_payload = get_next(recon_iter)

        elif live_id_int is not None and (recon_id_int is None or live_id_int < recon_id_int):
            issues.append(f"EXTRA in live table (not in ledger): ID {live_id}")
            live_id, live_payload = get_next(live_iter)

        elif recon_id_int == live_id_int:
            recon_hash = compute_record_hash(recon_id, recon_payload, fields_to_hash=fields_to_hash)
            live_hash = compute_record_hash(live_id, live_payload, fields_to_hash=fields_to_hash)

            if recon_hash != live_hash:
                issues.append(f"HASH MISMATCH for ID {live_id}")

            recon_id, recon_payload = get_next(recon_iter)
            live_id, live_payload = get_next(live_iter)

    return issues


# ============================================================
# === Main Verification Command ==============================
# ============================================================

def verify_table_command(
    table_name: str = typer.Argument(..., help="The logical table name to verify."),
    force: bool = typer.Option(False, "--force", help="Force re-computation and storage of a new Merkle root."),
    live: bool = typer.Option(False, "--live", help="Verify live table state against reconstructed state from ledger."),
    comprehensive: bool = typer.Option(
        False, "--comprehensive", help="Perform both stored root verification and live state verification."
    ),
    filters: Optional[List[str]] = typer.Option(None, "--filter", help="Filter by 'key:value'. Can be used multiple times."),
):
    """
    Unified verification command with multiple modes:

    Default:
        Verify stored Merkle root against computed root from ledger.
    --live:
        Verify live table state against reconstructed state from ledger.
    --comprehensive:
        Perform both verification modes.
    --force:
        Force re-computation and storage of a new Merkle root.
    """
    if force:
        console.print(f"Forcing re-computation and storage of new Merkle root for [bold cyan]{table_name}[/]...")
        new_root = compute_and_store_merkle_root(table_name)
        if new_root:
            console.print(f"[green]✓[/green] New root [bold]{new_root}[/bold] stored successfully.")
        else:
            console.print(f"[yellow]No data found for {table_name}, no root stored.[/yellow]")
        return

    # Determine verification modes
    verify_stored = not live and not comprehensive
    verify_live = live or comprehensive

    if verify_stored and verify_live:
        console.print(f"Performing comprehensive verification of [bold cyan]{table_name}[/]...")
    elif verify_stored:
        console.print(f"Verifying stored checkpoint integrity for [bold cyan]{table_name}[/]...")
    else:
        console.print(f"Verifying live table state for [bold cyan]{table_name}[/]...")

    conn = get_connection()
    cfg = get_config()

    try:
        # ------------------------------------------------------------
        # Mode 1: Verify stored root against computed root
        # ------------------------------------------------------------
        if verify_stored:
            console.print("\n[bold]Mode 1: Stored Root Verification[/bold]")
            stored_root_data = get_latest_merkle_root(table_name)

            if not stored_root_data:
                console.print(f"[bold yellow]No stored Merkle root found for '{table_name}'. Nothing to verify.[/bold yellow]")
                console.print("You can create one with: `maria-ledger verify --force`")
                if not verify_live:
                    raise typer.Exit()
            else:
                stored_root, computed_at = stored_root_data
                console.print(f" - Latest stored root: [bold white]{stored_root}[/bold white] (from {computed_at})")

                live_computed_root = compute_root_from_chain_hashes(conn, table_name)
                if not live_computed_root:
                    console.print("[bold red]❌ FAILURE: Stored root exists, but ledger appears empty or corrupted.[/bold red]")
                    if not verify_live:
                        raise typer.Exit(code=1)
                else:
                    console.print(f" - Live computed root: [bold white]{live_computed_root}[/bold white]")

                    if stored_root == live_computed_root:
                        console.print("[bold green]✅ SUCCESS: Stored checkpoint verified.[/bold green]")
                    else:
                        console.print("[bold red]❌ TAMPERING DETECTED: Stored checkpoint mismatch![/bold red]")
                        if not verify_live:
                            raise typer.Exit(code=1)

        # ------------------------------------------------------------
        # Mode 2: Verify live table state against reconstructed state
        # ------------------------------------------------------------
        if verify_live:
            console.print("\n[bold]Mode 2: Live State Verification[/bold]")
            fields_to_hash = ["name", "email"]  # Critical fields for integrity
            console.print(f"Verifying against critical fields: [bold yellow]id, {', '.join(fields_to_hash)}[/bold yellow]")

            # Reconstruct state from ledger
            console.print("Reconstructing state from ledger...")
            reconstructed_state, reconstructed_root = reconstruct_table_state(
                conn, table_name, filters=filters, fields_to_hash=fields_to_hash
            )
            console.print(f" [green]✓[/green] Reconstructed Merkle root: [bold]{reconstructed_root}[/bold]")

            # Compute Merkle root from live table
            console.print(f"Computing Merkle root from live table '{table_name}'...")
            live_root = get_merkle_root_of_current_state(
                conn, table_name, filters=filters, fields_to_hash=fields_to_hash
            )
            console.print(f" [green]✓[/green] Live table Merkle root: [bold]{live_root}[/bold]")

            # Compare roots
            if reconstructed_root == live_root:
                console.print("[bold green]✅ SUCCESS: Live table state matches the ledger.[/bold green]")
            else:
                console.print("[bold red]❌ FAILURE: Live state mismatch detected![/bold red]")
                console.print("Finding discrepancies...")

                live_stream = load_current_state_stream(conn, table_name, filters=filters)
                try:
                    discrepancies = find_discrepancies(
                        reconstructed_state, live_stream, fields_to_hash=fields_to_hash
                    )
                    for issue in discrepancies:
                        console.print(f" - [yellow]{issue}[/yellow]")
                    raise typer.Exit(code=1)
                finally:
                    from collections import deque
                    deque(live_stream, maxlen=0)

        # ------------------------------------------------------------
        # Final summary
        # ------------------------------------------------------------
        if verify_stored and verify_live:
            console.print("\n[bold green]✅ Comprehensive verification completed successfully![/bold green]")

    finally:
        conn.close()
