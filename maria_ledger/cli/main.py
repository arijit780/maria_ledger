import typer
from typing import List, Optional
from maria_ledger.cli.verify import verify_table_command
from maria_ledger.cli.audit import run as audit_command
from maria_ledger.cli.cli_forensic import forensic_command
from maria_ledger.cli.reconstruct import reconstruct_command
from maria_ledger.cli.bootstrap import bootstrap_command
from maria_ledger.cli.verify_chain import verify_chain_command
from maria_ledger.cli.snapshot import snapshot_command
from maria_ledger.cli.timeline import timeline_command

app = typer.Typer(help="Maria-Ledger CLI — verify and audit tamper-evident ledgers.")

# Core commands
app.command("verify")(verify_table_command)
app.command("audit")(audit_command)
app.command("forensic")(forensic_command)
app.command("bootstrap")(bootstrap_command)
app.command("verify-chain")(verify_chain_command)
app.command("snapshot")(snapshot_command)
app.command("timeline")(timeline_command)

# Wrapped commands with filters
@app.command("reconstruct")
def reconstruct_with_filter(
    table_name: str = typer.Argument(..., help="The logical table name to reconstruct."),
    out_csv: Optional[str] = typer.Option(None, "--out-csv", help="Path to write the reconstructed state as a CSV file."),
    filters: Optional[List[str]] = typer.Option(None, "--filter", help="Filter by 'key:value'. Can be used multiple times."),
):
    """Reconstruct a table's state from the ledger, with optional filters."""
    from maria_ledger.cli.reconstruct import reconstruct_command

    reconstruct_command(
        table_name=table_name,
        out_csv=out_csv,
        filters=filters,
    )

def main():
    app()

if __name__ == "__main__":
    main()

"""
Command-Line Interface (CLI) Usage
The maria-ledger CLI provides a suite of tools for managing, auditing, and verifying the integrity of your ledger tables.

CORE COMMANDS:

verify (UNIFIED)
Unified verification command with multiple modes:
- Default: Verify stored Merkle root against computed root from ledger
- --live: Verify live table state against reconstructed state from ledger
- --comprehensive: Perform both verification modes
- --force: Force re-computation and storage of a new Merkle root

Examples:
maria-ledger verify customers # Stored root verification
maria-ledger verify customers --live # Live state verification
maria-ledger verify customers --comprehensive # Both verification modes
maria-ledger verify customers --force # Force recompute + store root

audit
Runs a periodic integrity check on all tables tracked by the ledger.

What it does:
- Identifies all tables present in the ledger
- For each table, compares the latest stored Merkle root against a freshly computed root
- Reports any mismatches, which would indicate tampering

Example:
maria-ledger audit

reconstruct
Reconstructs a table's state to a specific point in time from the ledger.

What it does:
- Reads all ledger entries for a table up to a given transaction ID
- Applies them in order and calculates the final Merkle root
- Can save the reconstructed state to a CSV file

Example:
maria-ledger reconstruct customers --as-of-tx-order 150 --out-csv state_at_150.csv

timeline
Shows the chronological audit history for a single record.

What it does:
- Displays all changes to a specific record over time
- Shows INSERT, UPDATE, DELETE operations with timestamps
- Optional hash chain verification

Example:
maria-ledger timeline customers --id 15

forensic
Performs deep forensic analysis on the universal ledger's transaction chain.

What it does:
- Analyzes ledger entries for anomalies and tampering patterns
- Generates a report with risk score
- Detects hash chain breaks, timestamp inconsistencies, etc.

Example:
maria-ledger forensic customers --detail 3 --out report.json

snapshot
Creates a signed, immutable snapshot of a table's state.

What it does:
- Reconstructs table state from ledger
- Signs the Merkle root with private key
- Exports as JSON manifest

Example:
maria-ledger snapshot customers --out manifest.json

verify-chain
Verifies the cryptographic hash chain integrity of the universal ledger.

What it does:
- Validates hash chain continuity for a specific table
- Detects any breaks in the cryptographic chain
- Ensures data integrity at the ledger level

Example:
maria-ledger verify-chain customers

bootstrap
Brings an existing table under ledger control.

What it does:
- Snapshots existing data into the ledger
- Attaches database triggers for future changes
- Creates initial Merkle root checkpoint

Example:
maria-ledger bootstrap existing_table

trustmap
Manages cross-ledger trust relationships between tables.

What it does:
- Establishes trust relationships between ledger tables
- Cross-references Merkle roots for multi-table verification
- Verifies existing cross-references

Example:
maria-ledger trustmap ledger_customers ledger_orders

DEPRECATED COMMANDS:

verify-rows [DEPRECATED]
Legacy command for verifying individual row hashes.
Use 'maria-ledger verify-chain' instead for universal ledger verification.

verify-state [REMOVED]
Functionality merged into 'maria-ledger verify --live'.
"""