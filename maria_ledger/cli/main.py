import typer
from maria_ledger.cli.verify import verify_table_command
from maria_ledger.cli.diff import diff_table_command
from maria_ledger.cli.audit import run as audit_command
from maria_ledger.cli.append import append_record_command
from maria_ledger.cli.trustmap import trustmap_command
from maria_ledger.cli.cli_forensic import forensic_command
from maria_ledger.cli.reconstruct import reconstruct_command
from maria_ledger.cli.verify_state import verify_state_command

app = typer.Typer(help="Maria-Ledger CLI — verify and audit tamper-evident ledgers.")

# Subcommands
app.command("verify")(verify_table_command)
app.command("diff")(diff_table_command)
app.command("audit")(audit_command)
# app.command("append")(append_record_command)
# app.command("trustmap")(trustmap_command)
app.command("forensic")(forensic_command)
app.command("reconstruct")(reconstruct_command)
app.command("verify-state")(verify_state_command)

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