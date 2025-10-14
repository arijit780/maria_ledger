import typer
from maria_ledger.cli.verify import verify_table_command
from maria_ledger.cli.diff import diff_table_command
from maria_ledger.cli.audit import run as audit_command

app = typer.Typer(help="Maria-Ledger CLI — verify and audit tamper-evident ledgers.")

# Subcommands
app.command("verify")(verify_table_command)
app.command("diff")(diff_table_command)
app.command("audit")(audit_command)

def main():
    app()

if __name__ == "__main__":
    main()
