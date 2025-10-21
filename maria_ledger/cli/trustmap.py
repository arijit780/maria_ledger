"""CLI command for managing cross-ledger trust relationships."""

import typer
from rich.console import Console
from rich.table import Table
from datetime import datetime
from maria_ledger.db.cross_reference import record_cross_reference, verify_cross_reference
from maria_ledger.utils.formatter import pretty_time

console = Console()

def trustmap_command(
    ledger_a: str = typer.Argument(..., help="First ledger table name"),
    ledger_b: str = typer.Argument(..., help="Second ledger table name"),
    record: bool = typer.Option(False, "--record", "-r", help="Record a new cross-reference between ledgers"),
    verify: bool = typer.Option(True, help="Verify existing cross-references between ledgers"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format")
):
    """
    Manage and verify cross-ledger trust relationships.
    
    This command allows you to establish and verify trust relationships between
    two ledger tables by cross-referencing their Merkle roots.
    """
    if record:
        if not record_cross_reference(ledger_a, ledger_b):
            typer.echo("Failed to record cross-reference", err=True)
            raise typer.Exit(1)
        typer.echo(f"✓ Recorded cross-reference between {ledger_a} and {ledger_b}")

    if verify:
        results = verify_cross_reference(ledger_a, ledger_b)
        
        if json_output:
            # Convert datetime to string for JSON
            if results.get("last_verified"):
                results["last_verified"] = results["last_verified"].isoformat()
            import json
            typer.echo(json.dumps(results, indent=2))
            return

        # Rich table output
        table = Table(title=f"Cross-Ledger Trust Status: {ledger_a} ⟷ {ledger_b}")
        
        table.add_column("Check", style="cyan")
        table.add_column("Status", style="green")
        
        # Overall status
        table.add_row(
            "Cross-Reference Valid",
            "✓ Valid" if results["cross_refs_valid"] else "✗ Invalid"
        )
        
        # Current roots
        table.add_row(
            f"{ledger_a} Current Root",
            results["source_current_root"] or "Not found"
        )
        table.add_row(
            f"{ledger_b} Current Root",
            results["target_current_root"] or "Not found"
        )
        
        # Last verification
        if results["last_verified"]:
            table.add_row(
                "Last Verified",
                pretty_time(results["last_verified"])
            )
        
        console.print(table)
        
        # Print any errors
        if results["errors"]:
            console.print("\n[red]Errors found:[/red]")
            for error in results["errors"]:
                console.print(f"  • {error}")
        
        if not results["cross_refs_valid"]:
            raise typer.Exit(1)