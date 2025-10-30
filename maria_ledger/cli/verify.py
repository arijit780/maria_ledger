"""
verify.py

CLI command to verify a table's integrity against the latest signed Merkle root checkpoint.
"""
import typer
from rich.console import Console

from maria_ledger.db.connection import get_connection
from maria_ledger.db.merkle_service import get_latest_merkle_root, compute_root_from_chain_hashes
from maria_ledger.crypto.signer import verify_signature
from maria_ledger.utils.config import get_config

console = Console()


def verify_table_command(
    table_name: str = typer.Argument(..., help="The logical table name to verify."),
    force: bool = typer.Option(False, "--force", help="Force re-computation and storage of a new Merkle root."),
):
    """
    Verify the ledger's integrity against the latest signed Merkle root.

    This command performs two checks:
    1. Re-computes the Merkle root from the ledger's hash chain and compares it to the latest one stored in `ledger_roots`.
    2. Verifies the digital signature on the stored root.
    """
    from maria_ledger.db.merkle_service import compute_and_store_merkle_root

    if force:
        console.print(f"Forcing re-computation and storage of new Merkle root for [bold cyan]{table_name}[/]...")
        new_root = compute_and_store_merkle_root(table_name)
        if new_root:
            console.print(f"[green]✓[/green] New root [bold]{new_root}[/bold] stored successfully.")
        else:
            console.print(f"[yellow]No data found for {table_name}, no root stored.[/yellow]")
        return

    console.print(f"Verifying integrity of [bold cyan]{table_name}[/] against its latest checkpoint...")
    conn = get_connection()
    cfg = get_config()

    try:
        # 1. Get the latest signed root from the database
        stored_root_data = get_latest_merkle_root(table_name)
        if not stored_root_data:
            console.print(f"[bold yellow]No stored Merkle root found for '{table_name}'. Nothing to verify.[/bold yellow]")
            console.print("You can create one with: `maria-ledger verify --force`")
            raise typer.Exit()

        stored_root, computed_at = stored_root_data
        console.print(f"  - Latest stored root: [bold white]{stored_root}[/bold white] (from {computed_at})")

        # 2. Re-compute the Merkle root from the ledger's chain_hash values
        console.print("  - Re-computing root from ledger's hash chain...")
        live_computed_root = compute_root_from_chain_hashes(conn, table_name)

        if not live_computed_root:
            console.print("[bold red]❌ FAILURE: Stored root exists, but ledger appears empty or corrupted.[/bold red]")
            raise typer.Exit(code=1)

        console.print(f"  - Live computed root: [bold white]{live_computed_root}[/bold white]")

        # 3. Compare the roots
        if stored_root == live_computed_root:
            console.print("[bold green]✅ SUCCESS: Ledger integrity verified. The live ledger matches the signed checkpoint.[/bold green]")
        else:
            console.print("[bold red]❌ TAMPERING DETECTED: The ledger's history does not match the signed checkpoint![/bold red]")
            console.print("  - The `ledger` table may have been altered after the last checkpoint was signed.")
            raise typer.Exit(code=1)

        # 4. Verify the signature (if public key is available)
        # This part is left for a future phase involving key management.

    finally:
        conn.close()