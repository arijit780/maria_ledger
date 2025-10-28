import typer
from typing import List, Optional
from maria_ledger.cli.verify import verify_table_command
from maria_ledger.cli.audit import run as audit_command
from maria_ledger.cli.append import append_record_command
from maria_ledger.cli.trustmap import trustmap_command
from maria_ledger.cli.cli_forensic import forensic_command
from maria_ledger.cli.reconstruct import reconstruct_command
from maria_ledger.cli.verify_state import verify_state_command

app = typer.Typer(help="Maria-Ledger CLI — verify and audit tamper-evident ledgers.")

# Subcommands
app.command("verify")(verify_table_command)
app.command("audit")(audit_command)
# app.command("append")(append_record_command)
# app.command("trustmap")(trustmap_command)
app.command("forensic")(forensic_command)

# We need to wrap the commands in a function to add the new shared option
@app.command("reconstruct")
def reconstruct_with_filter(
    ctx: typer.Context,
    filters: Optional[List[str]] = typer.Option(None, "--filter", help="Filter by 'key:value'. Can be used multiple times."),
):
    """Reconstruct a table's state from the ledger, with optional filters."""
    reconstruct_command(ctx.args[0], **ctx.params)

@app.command("verify-state")
def verify_state_with_filter(
    ctx: typer.Context,
    filters: Optional[List[str]] = typer.Option(None, "--filter", help="Filter by 'key:value'. Can be used multiple times."),
):
    """Verify a table's current state against the ledger, with optional filters."""
    # The first argument is the table name, which is not a named parameter in the context
    verify_state_command(ctx.args[0], **ctx.params)

def main():
    app()

if __name__ == "__main__":
    main()
'''
maria-ledger reconstruct customers
Verify Live Table State:

bash
maria-ledger verify-state customers
Verify Against Stored Checkpoint: (This now works correctly)

bash
# Verify using the latest stored root
maria-ledger verify customers

# Force a re-computation and update of the stored root
maria-ledger verify customers --force
Run Periodic Audit:

bash
maria-ledger audit
Diff Between Two Points in Time:

bash
# Compare the state after transaction 100 vs. after transaction 200
maria-ledger diff customers --from-tx 100 --to-tx 200
Run Forensic Analysis:

bash
maria-ledger forensic customers
'''


'''
Command-Line Interface (CLI) Usage
The maria-ledger CLI provides a suite of tools for managing, auditing, and verifying the integrity of your ledger tables.

verify
Verifies the integrity of a table's most recent Merkle root checkpoint against both the current state of the ledger and its digital signature.

What it does:
Retrieves the latest stored Merkle root and its signature from the ledger_roots table.
Reconstructs the table state from the ledger to compute a "live" Merkle root.
Compares the stored root with the computed root to check for tampering.
Verifies the digital signature on the stored root using a configured public key.
When to use it: To confirm that the last official checkpoint (ledger_roots) is valid and hasn't been tampered with.
Example:
bash
maria-ledger verify customers --public-key /path/to/key.pub
verify-state
Verifies if the current state of a live data table (e.g., customers) perfectly matches the state reconstructed from the immutable ledger.

What it does:
Reconstructs the complete state of a table by replaying all INSERT, UPDATE, and DELETE operations from the ledger.
Computes a Merkle root from this reconstructed state.
Computes a Merkle root directly from the live data table.
Compares the two roots. If they differ, it performs a row-by-row comparison to find specific discrepancies (missing, extra, or modified rows).
When to use it: To check if the live, mutable table has been altered outside of the ledger's control. This is a crucial command for detecting unauthorized direct database modifications.
Example:
bash
maria-ledger verify-state customers
reconstruct
Reconstructs a table's state to a specific point in time (or the latest) from the ledger and outputs its Merkle root.

What it does: Reads all ledger entries for a table up to a given transaction ID, applies them in order, and calculates the final Merkle root. It can also save the reconstructed state to a CSV file.
When to use it: For debugging, auditing, or creating a snapshot of historical data.
Example:
bash
maria-ledger reconstruct customers --as-of-tx-order 150 --out-csv state_at_150.csv
diff
Shows the differences (added, modified, deleted rows) for a table between two points in time in the ledger's history.

What it does: Reconstructs the table state at two different transaction IDs (--from-tx and --to-tx) and compares the two snapshots.
When to use it: To understand exactly what changed in a table over a specific period.
Example:
bash
maria-ledger diff customers --from-tx 100 --to-tx 200
audit
Runs a periodic integrity check on all tables tracked by the ledger.

What it does:
Identifies all tables present in the ledger.
For each table, it compares the latest stored Merkle root in ledger_roots against a freshly computed root from the ledger data.
Reports any mismatches, which would indicate tampering.
When to use it: As a scheduled job (e.g., cron) to continuously monitor the integrity of all ledgers.
Example:
bash
maria-ledger audit
forensic
Performs a deep forensic analysis on the universal ledger's transaction chain for a specific table.

What it does: Analyzes the sequence of ledger entries, looking for anomalies like hash chain breaks, timestamp inconsistencies, or other patterns that could indicate sophisticated tampering. It generates a report with a risk score.
When to use it: When you suspect tampering and need to perform a deeper investigation than a simple Merkle root check.
Example:
bash
maria-ledger forensic customers --detail 3 --out report.json
'''