"""CLI command for forensic analysis of temporal ledger data."""

import typer
from rich.console import Console
from rich.table import Table
from pathlib import Path
import json
from maria_ledger.db.connection import get_connection
from maria_ledger.db.temporal_utils import analyze_universal_ledger_chain
from maria_ledger.utils.formatter import pretty_time

console = Console()

def forensic_command(
    table_name: str = typer.Argument(..., help="Name of the ledger table to analyze"),
    output_file: Path = typer.Option(None, "--out", "-o", help="Write report to file"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format"),
    detail_level: int = typer.Option(1, "--detail", "-d", help="Level of detail in the report (1-3)")
):
    """
    Perform forensic analysis on a temporal ledger table.
    
    This command analyzes the temporal chain of records in a ledger table,
    looking for anomalies, gaps, or potential tampering evidence.
    """
    try:
        report = analyze_universal_ledger_chain(table_name)
        
        if json_output:
            typer.echo(json.dumps(report, indent=2))
            return

        # Rich table output for summary
        summary_table = Table(title=f"Forensic Analysis: {table_name}")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Table", report['table'])
        summary_table.add_row("Rows Scanned", str(report['rows_scanned']))
        summary_table.add_row("Anomalies Found", str(report['anomaly_count']))
        summary_table.add_row("Risk Score", f"{report['risk_score']} / 100")
        
        console.print(summary_table)
        
        # Detailed anomalies table if any found
        if report['anomalies']:
            console.print("\n[yellow]Detected Anomalies:[/yellow]")
            anomaly_table = Table(show_header=True)
            anomaly_table.add_column("Type", style="red")
            anomaly_table.add_column("Details", style="yellow")
            anomaly_table.add_column("Severity", style="magenta")
            
            # Show more details based on detail level
            anomaly_limit = {1: 5, 2: 10, 3: None}[detail_level]
            anomalies = report['anomalies'][:anomaly_limit] if anomaly_limit else report['anomalies']
            
            for anomaly in anomalies:
                anomaly_table.add_row(
                    anomaly['type'],
                    anomaly.get('detail', 'No details available'),
                    anomaly.get('severity', 'Unknown')
                )
            
            console.print(anomaly_table)
        
        # Save to file if requested
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            typer.echo(f"\nReport written to {output_file}")
            
        # Exit with error if high-risk anomalies found
        if report['risk_score'] > 75:
            console.print("\n[red]⚠️  High-risk anomalies detected![/red]")
            raise typer.Exit(1)
            
    except Exception as e:
        console.print(f"\n[red]Error during analysis:[/red] {str(e)}")
        raise typer.Exit(1)
