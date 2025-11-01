import typer
from rich.console import Console
from maria_ledger.utils.bootstrap_utils import bootstrap_table_core

console = Console()


def bootstrap_command(
    table_name: str = typer.Argument(..., help="The existing table to bring under ledger control."),
):
    """
    Bootstrap an existing table by snapshotting its data into the ledger,
    attaching triggers, and creating an initial Merkle root checkpoint.
    """
    console.print(f"Bootstrapping table [bold cyan]{table_name}[/]...")

    try:
        # Use the core bootstrap function
        result = bootstrap_table_core(
            table_name=table_name,
            fields=None,  # Track all columns
            primary_key=None,  # Auto-detect
            snapshot_existing=True,
            create_checkpoint=True,
        )

        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            console.print(f"\n[bold red]❌ ERROR:[/bold red] {error_msg}")
            raise typer.Exit(code=1)

        # Step 1: Snapshot existing data
        console.print(" - Step 1: Snapshotting existing data...")
        if result["records_snapshotted"] > 0:
            console.print(
                f" - [green]✓[/green] Snapshotted {result['records_snapshotted']} records into the ledger."
            )
        else:
            console.print(
                f" - [yellow]Warning:[/yellow] Table '{table_name}' is empty. Skipping snapshot."
            )

        # Step 2: Attach triggers
        console.print(" - Step 2: Attaching database triggers...")
        console.print(f" - [green]✓[/green] Attached INSERT, UPDATE, and DELETE triggers.")
        console.print(f" Tracking columns: {', '.join(result['columns_tracked'])}")
        console.print(f" Primary key: {result['primary_key']}")

        # Step 3: Create Merkle checkpoint
        console.print(" - Step 3: Creating initial Merkle root checkpoint...")
        if result["merkle_root"]:
            console.print(
                f" - [green]✓[/green] Initial checkpoint created. Root: [bold white]{result['merkle_root']}[/bold white]"
            )
        else:
            console.print(
                " - [yellow]Warning:[/yellow] Could not create checkpoint, table might be empty."
            )

        console.print(
            f"\n[bold green]✅ Bootstrap Complete![/bold green] Table '{table_name}' is now under ledger control."
        )

    except Exception as e:
        console.print(f"\n[bold red]❌ ERROR:[/bold red] {e}")
        console.print("Bootstrap failed. Any changes have been rolled back.")
        raise typer.Exit(code=1)
