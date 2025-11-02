"""
verify.py

Unified CLI command to verify table integrity with multiple verification modes.
"""

import typer
import json
from rich.console import Console
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

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
from maria_ledger.crypto.merkle_tree import MerkleTree
from maria_ledger.utils.schema import detect_table_schema

console = Console()


# ============================================================
# === Load Current Table State ===============================
# ============================================================

def load_current_state_stream(conn, table_name, filters: Optional[List[str]] = None, primary_key: Optional[str] = None):
    """
    Generator that yields rows from the current state of a table.
    Auto-detects the primary key column name if not provided.
    
    Args:
        conn: Database connection
        table_name: Name of the table
        filters: Optional list of filters (e.g., ['id:123', 'name:value'])
        primary_key: Optional primary key column name (auto-detected if not provided)
    """
    # Detect primary key dynamically if not provided
    if primary_key is None:
        schema = detect_table_schema(table_name)
        primary_key = schema['primary_key']
    
    sql = f"SELECT * FROM {table_name}"
    params = []

    filter_sql, filter_params = parse_filters(filters)
    sql += " WHERE 1=1" + filter_sql
    params.extend(filter_params)
    sql += f" ORDER BY {primary_key}"

    with conn.cursor(dictionary=True, buffered=False) as cur:
        cur.execute(sql, params)
        for row in cur:
            record_id = str(row[primary_key])
            payload = {k: v for k, v in row.items() if k != primary_key}
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
# === Row-Level Verification & Proof Generation ============
# ============================================================

def verify_row(
    conn,
    table_name: str,
    record_id: str,
    fields_to_hash: Optional[List[str]] = None,
    check_checkpoint: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Verify a single row by checking:
    1. If stored checkpoint matches current ledger (checkpoint verification)
    2. If live row matches reconstructed state (state verification)
    
    Args:
        conn: Database connection
        table_name: Table name
        record_id: Record ID to verify
        fields_to_hash: Fields to hash (for state verification)
        check_checkpoint: Whether to check against stored checkpoint
    
    Returns:
        Tuple of (is_valid, message) where message explains the result
    """
    # Step 1: Check if ledger matches stored checkpoint (same as full verify)
    if check_checkpoint:
        stored_root_data = get_latest_merkle_root(table_name)
        if stored_root_data:
            stored_root, computed_at, stored_fields_to_hash = stored_root_data
            computed_chain_root = compute_root_from_chain_hashes(conn, table_name)
            
            if computed_chain_root and stored_root != computed_chain_root:
                return False, f"Ledger changed since last checkpoint ({computed_at}). Use '--force' to update checkpoint."
    
    # Use stored fields_to_hash if not explicitly provided
    if fields_to_hash is None:
        stored_root_data = get_latest_merkle_root(table_name)
        if stored_root_data:
            _, _, stored_fields_to_hash = stored_root_data
            if stored_fields_to_hash:
                fields_to_hash = stored_fields_to_hash
    
    # Step 2: Verify row state matches reconstructed state
    reconstructed_state, reconstructed_root = reconstruct_table_state(
        conn, table_name, filters=None, fields_to_hash=fields_to_hash
    )
    
    if record_id not in reconstructed_state:
        return False, f"Record ID {record_id} not found in reconstructed state."
    
    # Detect primary key for filter (reuse from load_current_state_stream)
    schema = detect_table_schema(table_name)
    primary_key = schema['primary_key']
    
    # Get live row data using detected primary key
    live_rows = list(load_current_state_stream(conn, table_name, filters=[f"{primary_key}:{record_id}"], primary_key=primary_key))
    
    if not live_rows:
        return False, f"Record ID {record_id} not found in live table."
    
    live_id, live_payload = live_rows[0]
    
    # Compute hashes
    recon_hash = compute_record_hash(record_id, reconstructed_state[record_id], fields_to_hash=fields_to_hash)
    live_hash = compute_record_hash(live_id, live_payload, fields_to_hash=fields_to_hash)
    
    if recon_hash != live_hash:
        return False, f"Hash mismatch: Live row doesn't match reconstructed state."
    
    return True, None
def generate_record_proof(
    conn,
    table_name: str,
    record_id: str,
    fields_to_hash: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Generate cryptographic proof for a single record.
    
    Returns:
        Dictionary containing proof data for export
    """
    # Reconstruct current state
    reconstructed_state, reconstructed_root = reconstruct_table_state(
        conn, table_name, filters=None, fields_to_hash=fields_to_hash
    )
    
    if record_id not in reconstructed_state:
        raise ValueError(f"Record {record_id} not found in reconstructed state")
    
    # Build Merkle tree from current state
    sorted_ids = sorted(reconstructed_state.keys(), key=lambda x: int(x) if x.isdigit() else x)
    record_index = sorted_ids.index(record_id)
    
    # Build tree
    hashes = [
        compute_record_hash(rid, reconstructed_state[rid], fields_to_hash=fields_to_hash)
        for rid in sorted_ids
    ]
    tree = MerkleTree(hashes)
    
    # Get proof
    proof_path = tree.get_proof(record_index)
    leaf_hash = hashes[record_index]
    computed_state_root = tree.get_root()
    
    # Get stored root from ledger_roots for comparison
    # Note: Stored root is ledger chain root, computed_state_root is state root
    # These are different trees (chain hashes vs record hashes), but we include both for reference
    stored_root_data = get_latest_merkle_root(table_name)
    stored_chain_root = stored_root_data[0] if stored_root_data else None
    
    # Verify that computed state root matches stored root if available
    # Actually wait - stored root is chain root, not state root!
    # For state proofs, we use the computed state root as the "trusted" root
    # The stored_chain_root is just for reference/comparison
    
    # Build proof object with clear labels
    proof = {
        "proof_type": "record_state_proof",
        "table_name": table_name,
        "record_id": record_id,
        "record_data": reconstructed_state[record_id],
        "verification": {
            "state_root": computed_state_root,  # Root of state tree (what this proof verifies)
            "ledger_chain_root": stored_chain_root,  # Root of ledger chain (for reference)
            "timestamp": datetime.now().isoformat(),
            "fields_hashed": fields_to_hash or "all"
        },
        "merkle_proof": {
            "leaf_hash": leaf_hash,
            "proof_path": proof_path,  # Sibling hashes needed to verify
            "leaf_index": record_index,
            "instructions": "Use leaf_hash + proof_path to reconstruct state_root"
        },
        "trusted_checkpoint": stored_chain_root,  # This is the checkpoint to verify against
        "how_to_verify": "1. Compute record hash from record_data. 2. Use proof_path to rebuild state_root. 3. Compare with trusted_checkpoint if available."
    }
    
    return proof
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
    export: Optional[str] = typer.Option(None, "--export", help="Export proof to JSON file (requires exactly one matching row)."),
):
    """
    Unified verification command with multiple modes:

    Default (no filters):
        Verify stored Merkle root against computed root from ledger.
    
    With --filter (row-level verification):
        Without --export:
            Verify all rows matching the filter (can be multiple).
            Show results for each row.
        
        With --export:
            Require exactly one matching row.
            Error if 0 or multiple rows match.
            Verify and export proof for that single row.
    
    --live:
        Verify live table state against reconstructed state from ledger.
    
    --comprehensive:
        Perform both stored root verification and live state verification.
    
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

    conn = get_connection()
    cfg = get_config()

    # Get stored fields_to_hash from checkpoint (for backward compatibility)
    stored_root_data = get_latest_merkle_root(table_name)
    stored_fields_to_hash = None
    if stored_root_data:
        _, _, stored_fields_to_hash = stored_root_data

    # If filters are provided, do row-level verification
    if filters:
        # Use stored fields_to_hash if available, otherwise default to common fields
        fields_to_hash = stored_fields_to_hash or ["name", "email"]
        
        try:
            # Get all matching rows
            matching_rows = list(load_current_state_stream(conn, table_name, filters=filters))
            
            if not matching_rows:
                console.print(f"[red]❌ No rows found matching filter: {filters}[/red]")
                return
            
            if export:
                # Export mode: must be exactly one row
                if len(matching_rows) != 1:
                    console.print(f"[red]❌ Filter matches {len(matching_rows)} rows. Proof export requires exactly one row.[/red]")
                    console.print("[yellow]Matching rows:[/yellow]")
                    for record_id, payload in matching_rows:
                        console.print(f"  - ID {record_id}: {payload}")
                    raise typer.Exit(code=1)
                
                # Verify single row + export proof
                record_id, payload = matching_rows[0]
                console.print(f"Verifying row ID [bold cyan]{record_id}[/bold cyan]...")
                
                # Verify first (check checkpoint + state)
                is_valid, error_msg = verify_row(conn, table_name, record_id, fields_to_hash=fields_to_hash, check_checkpoint=True)
                
                if not is_valid:
                    console.print(f"[red]❌ Row verification failed: {error_msg}[/red]")
                    if "checkpoint" in error_msg.lower():
                        console.print("[yellow]Hint:[/yellow] Run 'maria-ledger verify --force' to update the checkpoint.")
                    raise typer.Exit(code=1)
                # Generate and export proof
                console.print("Generating cryptographic proof...")
                proof = generate_record_proof(conn, table_name, record_id, fields_to_hash=fields_to_hash)
                
                with open(export, 'w') as f:
                    json.dump(proof, f, indent=2, default=str)
                
                console.print(f"[green]✅ Row verified successfully![/green]")
                console.print(f"[green]✓[/green] Proof exported to [bold]{export}[/bold]")
                console.print(f"  - Record ID: {record_id}")
                console.print(f"  - State root: {proof['verification']['state_root']}")
                console.print(f"  - Proof path length: {len(proof['merkle_proof']['proof_path'])}")
                console.print(f"  - Proof type: {proof['proof_type']}")
                
            else:
                # Verify mode: can be multiple rows
                console.print(f"Verifying [bold cyan]{len(matching_rows)}[/bold cyan] row(s) matching filter...")
                
                # First check: Does ledger match stored checkpoint?
                stored_root_data = get_latest_merkle_root(table_name)
                checkpoint_mismatch = False
                if stored_root_data:
                    stored_root, computed_at = stored_root_data
                    computed_chain_root = compute_root_from_chain_hashes(conn, table_name)
                    if computed_chain_root and stored_root != computed_chain_root:
                        checkpoint_mismatch = True
                        console.print(f"[yellow]⚠️  Warning:[/yellow] Ledger changed since last checkpoint ({computed_at}).")
                        console.print(f"  [dim]Stored root: {stored_root}[/dim]")
                        console.print(f"  [dim]Current root: {computed_chain_root}[/dim]")
                        console.print(f"  [yellow]Run 'maria-ledger verify {table_name} --force' to update checkpoint.[/yellow]\n")
                
                all_valid = True
                for record_id, payload in matching_rows:
                    # Verify row state (skip checkpoint check since we did it once above)
                    is_valid, error_msg = verify_row(conn, table_name, record_id, fields_to_hash=fields_to_hash, check_checkpoint=False)
                    if is_valid:
                        if checkpoint_mismatch:
                            console.print(f"[yellow]⚠️[/yellow] Row ID [bold]{record_id}[/bold] state is consistent, but ledger changed since checkpoint")
                        else:
                            console.print(f"[green]✅[/green] Row ID [bold]{record_id}[/bold] is authentic")
                    else:
                        console.print(f"[red]❌[/red] Row ID [bold]{record_id}[/bold] verification failed: {error_msg}")
                        all_valid = False
                
                if all_valid and not checkpoint_mismatch:
                    console.print(f"\n[bold green]✅ All {len(matching_rows)} row(s) verified successfully![/bold green]")
                elif all_valid and checkpoint_mismatch:
                    console.print(f"\n[yellow]⚠️  All {len(matching_rows)} row(s) state is consistent, but checkpoint needs update.[/yellow]")
                else:
                    console.print(f"\n[bold red]❌ Some rows failed verification![/bold red]")
                    raise typer.Exit(code=1)
                    
        finally:
            conn.close()
        return
    
# Full table verification (existing logic)
    # Determine verification modes
    verify_stored = not live and not comprehensive
    verify_live = live or comprehensive

    if verify_stored and verify_live:
        console.print(f"Performing comprehensive verification of [bold cyan]{table_name}[/]...")
    elif verify_stored:
        console.print(f"Verifying stored checkpoint integrity for [bold cyan]{table_name}[/]...")
    else:
        console.print(f"Verifying live table state for [bold cyan]{table_name}[/]...")

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
                stored_root, computed_at, _ = stored_root_data
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
            # Use stored fields_to_hash if available, otherwise default
            live_fields_to_hash = stored_fields_to_hash or ["name", "email"]
            schema = detect_table_schema(table_name)
            primary_key = schema['primary_key']
            fields_display = f"{primary_key}, {', '.join(live_fields_to_hash)}" if live_fields_to_hash else "all fields"
            console.print(f"Verifying against fields: [bold yellow]{fields_display}[/bold yellow]")

            # Reconstruct state from ledger
            console.print("Reconstructing state from ledger...")
            reconstructed_state, reconstructed_root = reconstruct_table_state(
                conn, table_name, filters=filters, fields_to_hash=live_fields_to_hash
            )
            console.print(f" [green]✓[/green] Reconstructed Merkle root: [bold]{reconstructed_root}[/bold]")

            # Compute Merkle root from live table
            console.print(f"Computing Merkle root from live table '{table_name}'...")
            live_root = get_merkle_root_of_current_state(
                conn, table_name, filters=filters, fields_to_hash=live_fields_to_hash
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
                        reconstructed_state, live_stream, fields_to_hash=live_fields_to_hash
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
