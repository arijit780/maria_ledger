"""
snapshot.py

CLI command to create a signed, immutable snapshot of a table's state.
"""
import typer
import json
from datetime import datetime, timezone
import os

from rich.console import Console

from maria_ledger.db.connection import get_connection
from maria_ledger.cli.reconstruct import reconstruct_table_state
from maria_ledger.crypto.signer import sign_data
from maria_ledger.utils.config import get_config

console = Console()


def get_max_tx_order(conn, table_name: str) -> int:
    """Fetches the highest tx_order for a given table from the ledger."""
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(tx_order) FROM ledger WHERE table_name = %s", (table_name,))
        result = cur.fetchone()
        return result[0] if result and result[0] is not None else 0


def snapshot_command(
    table_name: str = typer.Argument(..., help="The logical table name to snapshot."),
    out_file: str = typer.Option(..., "--out", help="Path to write the snapshot JSON file."),
    store_root: bool = typer.Option(False, "--store-root", help="Also insert the root into the ledger_roots table."),
):
    """
    Create a signed, immutable snapshot of a table's state from the ledger.
    """
    console.print(f"Creating snapshot for table [bold cyan]{table_name}[/]...")
    conn = get_connection()
    cfg = get_config()

    try:
        # 1. Reconstruct state and get Merkle root
        console.print("  - Reconstructing table state from ledger...")
        state_dict, merkle_root = reconstruct_table_state(conn, table_name)
        if not state_dict:
            console.print("[yellow]Warning: Table has no records in its reconstructed state. Snapshot will be empty.[/yellow]")
        console.print(f"  - Merkle root computed: [bold white]{merkle_root}[/bold white]")

        # 2. Get metadata
        last_tx_order = get_max_tx_order(conn, table_name)
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        # 3. Sign the Merkle root
        console.print("  - Signing the Merkle root...")
        priv_key_path = cfg["crypto"]["private_key_path"]
        signature_b64 = sign_data(priv_key_path, merkle_root.encode('utf-8'))
        console.print(f"  - Signature created successfully.")

        # 4. Build the manifest
        manifest = {
            "table_name": table_name,
            "reconstructed_rows": len(state_dict),
            "last_tx_order": last_tx_order,
            "merkle_root": merkle_root,
            "timestamp_utc": timestamp_utc,
            "signature": signature_b64,
        }

        # 5. Write to file deterministically
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, sort_keys=True, separators=(',', ':'), indent=4)
        console.print(f"\n[green]✅ Snapshot created successfully at:[/] [yellow]{out_file}[/yellow]")

        # 6. Optionally store in ledger_roots
        if store_root:
            console.print("  - Storing root in `ledger_roots` table as requested...")
            # This re-uses the logic from the verify command's --force flag
            from maria_ledger.db.merkle_service import compute_and_store_merkle_root
            stored_root = compute_and_store_merkle_root(table_name)
            if stored_root:
                console.print(f"  - [green]✓[/green] Root stored in database.")
            else:
                console.print(f"  - [red]❌[/red] Failed to store root in database.")

    except FileNotFoundError:
        console.print(f"[bold red]❌ ERROR: Private key not found at '{priv_key_path}'. Check your config.toml.[/bold red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]❌ An unexpected error occurred: {e}[/bold red]")
        raise typer.Exit(code=1)
    finally:
        if conn and conn.is_connected():
            conn.close()