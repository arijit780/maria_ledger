"""
snapshot.py

CLI command to create a signed, immutable snapshot of a table's state.
"""

import typer
import json
import os
from datetime import datetime, timezone
from rich.console import Console

from maria_ledger.db.connection import get_connection
from maria_ledger.cli.reconstruct import reconstruct_table_state
from maria_ledger.crypto.signer import sign_merkle_root
from maria_ledger.utils.config import get_config

console = Console()


# ============================================================
# === Utility: Get Highest Ledger tx_order ===================
# ============================================================

def get_max_tx_order(conn, table_name: str) -> int:
    """Fetches the highest tx_order for a given table from the ledger."""
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(tx_order) FROM ledger WHERE table_name = %s", (table_name,))
        result = cur.fetchone()
        return result[0] if result and result[0] is not None else 0


# ============================================================
# === Snapshot Command =======================================
# ============================================================

def snapshot_command(
    table_name: str = typer.Argument(..., help="The logical table name to snapshot."),
    out_file: str = typer.Option(..., "--out", help="Path to write the snapshot JSON file."),
    store_root: bool = typer.Option(False, "--store-root", help="Also insert the root into the ledger_roots table."),
):
    """
    Create a signed, immutable snapshot of a table's state from the ledger.

    Steps:
        1. Reconstruct the full state from the ledger.
        2. Compute the Merkle root of that state.
        3. Sign the root using the private key from config.toml.
        4. Write a manifest file (deterministic JSON).
        5. Optionally, store the root in ledger_roots.
    """
    console.print(f"Creating snapshot for table [bold cyan]{table_name}[/]...")

    conn = get_connection()
    cfg = get_config()

    try:
        # ------------------------------------------------------------
        # Step 1: Reconstruct table state
        # ------------------------------------------------------------
        console.print("  - Reconstructing table state from ledger...")
        state_dict, merkle_root = reconstruct_table_state(conn, table_name)

        if not state_dict:
            console.print(
                "[yellow]Warning:[/yellow] Table has no records in its reconstructed state. Snapshot will be empty."
            )

        console.print(f"  - Merkle root computed: [bold white]{merkle_root}[/bold white]")

        # ------------------------------------------------------------
        # Step 2: Gather metadata
        # ------------------------------------------------------------
        last_tx_order = get_max_tx_order(conn, table_name)
        timestamp_utc = datetime.now(timezone.utc).isoformat()

        # ------------------------------------------------------------
        # Step 3: Sign Merkle root
        # ------------------------------------------------------------
        console.print("  - Signing the Merkle root...")
        priv_key_path = cfg["crypto"]["private_key_path"]
        signature_b64 = sign_merkle_root(priv_key_path, merkle_root)
        console.print("  - Signature created successfully.")

        # ------------------------------------------------------------
        # Step 4: Build manifest
        # ------------------------------------------------------------
        manifest = {
            "table_name": table_name,
            "reconstructed_rows": len(state_dict),
            "last_tx_order": last_tx_order,
            "merkle_root": merkle_root,
            "timestamp_utc": timestamp_utc,
            "signature": signature_b64,
        }

        # ------------------------------------------------------------
        # Step 5: Write manifest file
        # ------------------------------------------------------------
        os.makedirs(os.path.dirname(out_file), exist_ok=True)

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, sort_keys=True, separators=(",", ":"), indent=4)

        console.print(f"\n[green]✅ Snapshot created successfully at:[/] [yellow]{out_file}[/yellow]")

        # ------------------------------------------------------------
        # Step 6: Optional — store in ledger_roots
        # ------------------------------------------------------------
        if store_root:
            console.print("  - Storing root in `ledger_roots` table as requested...")
            from maria_ledger.db.merkle_service import compute_and_store_merkle_root

            stored_root = compute_and_store_merkle_root(table_name)
            if stored_root:
                console.print("  - [green]✓[/green] Root stored in database.")
            else:
                console.print("  - [red]❌[/red] Failed to store root in database.")

    except FileNotFoundError:
        console.print(f"[bold red]❌ ERROR:[/bold red] Private key not found at '{priv_key_path}'. Check your config.toml.")
        raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"[bold red]❌ An unexpected error occurred:[/bold red] {e}")
        raise typer.Exit(code=1)

    finally:
        if conn and conn.is_connected():
            conn.close()
