from typing import List, Optional

import typer
from rich.console import Console

from maria_ledger.cli.audit import run as audit_command
from maria_ledger.cli.bootstrap import bootstrap_command
from maria_ledger.cli.cli_forensic import forensic_command
from maria_ledger.cli.reconstruct import reconstruct_command
from maria_ledger.cli.snapshot import snapshot_command
from maria_ledger.cli.timeline import timeline_command
from maria_ledger.cli.trustmap import trustmap_command
from maria_ledger.cli.verify import verify_table_command
from maria_ledger.cli.verify_chain import verify_chain_command
from maria_ledger.cli.verify_rows import verify_rows_command


CLI_DESCRIPTION = """
Maria-Ledger CLI — A suite of tools for managing, auditing, and verifying the integrity of tamper-evident ledger tables.

CORE COMMANDS:

  - verify: Unified verification command for stored roots and live table state.
  - audit: Runs integrity checks on all tables tracked by the ledger.
  - reconstruct: Reconstructs a table's state from the ledger.
  - timeline: Shows the chronological audit history for a single record.
  - verify-chain: Verifies the cryptographic hash chain integrity of the ledger.
  - snapshot: Creates a signed, immutable snapshot of a table's state.
  - bootstrap: Brings an existing table under ledger control.
  - forensic: Performs deep forensic analysis on the transaction chain.
  - trustmap: Manages cross-ledger trust relationships between tables.
"""

app = typer.Typer(
    help="Maria-Ledger CLI — verify and audit tamper-evident ledgers.",
    rich_markup_mode="markdown",
    epilog=CLI_DESCRIPTION
)

# Core commands
app.command("verify")(verify_table_command)
app.command("audit")(audit_command)
app.command("forensic")(forensic_command)
app.command("bootstrap")(bootstrap_command)
app.command("reconstruct")(reconstruct_command)
app.command("verify-chain")(verify_chain_command)
app.command("snapshot")(snapshot_command)
app.command("timeline")(timeline_command)
app.command("trustmap")(trustmap_command)
# TODO: Implement and uncomment verify-snapshot command
# from maria_ledger.cli.verify_snapshot import verify_snapshot_command
# app.command("verify-snapshot")(verify_snapshot_command)

# Deprecated commands with warnings
@app.command("verify-rows")
def verify_rows_with_deprecation_warning(
    table: str = typer.Argument(..., help="Table name to verify"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed verification info"),
    json_output: bool = typer.Option(False, "--json", help="Output result in JSON format")
):
    """
        [DEPRECATED] Use 'maria-ledger verify-chain' instead.
    """
    console = Console()
    console.print(
        "[bold yellow]⚠️ WARNING: The 'verify-rows' command is deprecated. "
        "Please use 'verify-chain' for more robust ledger integrity checks.[/bold yellow]\n"
    )
    verify_rows_command(table, verbose, json_output)


def main():
    app()


if __name__ == "__main__":
    main()