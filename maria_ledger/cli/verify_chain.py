"""
verify_chain.py

CLI command to verify the integrity of the ledger's internal hash chain.
"""
import typer
from rich.console import Console
from rich.progress import Progress

from maria_ledger.db.connection import get_connection

from maria_ledger.crypto.hash_utils import compute_chain_hash

console = Console()


def verify_chain_command(
    table_name: str = typer.Argument(..., help="The logical table name to verify within the ledger.")
):
    """
    Verify the cryptographic hash chain of the ledger for a given table.
    """
    console.print(f"Verifying hash chain for table [bold cyan]{table_name}[/]...")
    conn = get_connection()
    try:
        with conn.cursor(dictionary=True, buffered=False) as cur:
            # Fetch total row count for the progress bar
            cur.execute("SELECT COUNT(*) as count FROM ledger WHERE table_name = %s", (table_name,))
            total_rows = cur.fetchone()['count']
            if total_rows == 0:
                console.print("[yellow]No ledger entries found for this table. Nothing to verify.[/yellow]")
                return

            # Fetch all rows to verify
            sql = "SELECT * FROM ledger WHERE table_name = %s ORDER BY tx_order ASC"
            cur.execute(sql, (table_name,))

            expected_prev_hash = '0' * 64  # The expected hash of the very first entry

            with Progress(console=console) as progress:
                task = progress.add_task("[green]Verifying entries...", total=total_rows)
                for row in cur:
                    # 1. Verify the link to the previous entry
                    if row['prev_hash'] != expected_prev_hash:
                        console.print(f"\n[bold red]FAILURE: Chain broken![/bold red]")
                        console.print(f"Mismatch at tx_order [bold]{row['tx_order']}[/]:")
                        console.print(f"  - Expected prev_hash: {expected_prev_hash}")
                        console.print(f"  - Found prev_hash:    {row['prev_hash']}")
                        raise typer.Exit(code=1)

                    # 2. Verify the integrity of the current row's hash
                    recomputed_hash = compute_chain_hash(
                        row['prev_hash'],
                        row['tx_id'],
                        row['record_id'],
                        row['op_type'],
                        row['old_payload'],
                        row['new_payload'],
                        row['created_at'],
                        
                    )
                    if row['chain_hash'] != recomputed_hash:
                        console.print(f"\n[bold red]FAILURE: Corrupted entry![/bold red]")
                        console.print(f"Hash mismatch for row at tx_order [bold]{row['tx_order']}[/]:")
                        console.print(f"  - Stored chain_hash:   {row['chain_hash']}")
                        console.print(f"  - Recomputed chain_hash: {recomputed_hash}")
                        raise typer.Exit(code=1)

                    expected_prev_hash = row['chain_hash']
                    progress.update(task, advance=1)

        console.print("\n[bold green]SUCCESS: Ledger hash chain is intact and valid.[/bold green]")

    finally:
        conn.close()