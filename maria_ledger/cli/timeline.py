"""
timeline.py

CLI command to replay the full audit history of a single record.
"""
import typer
import json
from rich.console import Console
from rich.style import Style

from maria_ledger.db.connection import get_connection
from maria_ledger.utils.helpers import json_serial

console = Console()


def format_payload_diff(op_type: str, old_payload: dict, new_payload: dict) -> str:
    print("new_payload",new_payload)
    print("old_payload",old_payload)
    """Creates a human-readable summary of what changed in a transaction."""
    if op_type == 'INSERT':
        return ", ".join(f"[green]{k}[/green]=[yellow]{v}[/yellow]" for k, v in (new_payload or {}).items())
    
    if op_type == 'DELETE':
        return ", ".join(f"[red]{k}[/red]=[yellow]{v}[/yellow]" for k, v in (old_payload or {}).items())

    if op_type == 'UPDATE':
        old = old_payload or {}
        new = new_payload or {}
        changes = []
        all_keys = sorted(list(set(old.keys()) | set(new.keys())))
        for k in all_keys:
            old_val = old.get(k)
            new_val = new.get(k)
            if old_val != new_val:
                changes.append(f"{k}: [red]{old_val}[/red] -> [green]{new_val}[/green]")
        return ", ".join(changes)

    return ""


def timeline_command(
    table_name: str = typer.Argument(..., help="The logical table name (e.g., 'customers')."),
    record_id: str = typer.Option(..., "--id", help="The ID of the record to trace."),
    verify_chain: bool = typer.Option(False, "--verify-chain", help="Validate hash chain continuity during replay."),
    json_output: bool = typer.Option(False, "--json", help="Output the timeline as a JSON array."),
):
    """
    Display the chronological audit history (timeline) for a single record.
    """
    conn = get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            sql = """
                SELECT tx_order, op_type, old_payload, new_payload, created_at, prev_hash, chain_hash
                FROM ledger
                WHERE table_name = %s AND record_id = %s
                ORDER BY tx_order ASC;
            """
            cur.execute(sql, (table_name, record_id))
            history = cur.fetchall()

        if not history:
            console.print(f"[yellow]No history found for table '{table_name}' with record ID '{record_id}'.[/yellow]")
            return

        if json_output:
            # Output as a clean JSON array
            print(json.dumps(history, default=json_serial, sort_keys=True, separators=(',', ':')))
            return

        console.print(f"Timeline for [cyan]{table_name}[/] ID [bold]{record_id}[/bold]:")

        expected_prev_hash = '0' * 64  # Genesis hash for the first entry in the entire ledger
        is_first_record_in_timeline = True
        chain_is_valid = True

        for row in history:
            op_type = row['op_type']
            created_at = row['created_at'].isoformat()
            
            # Parse payloads safely
            old_payload = json.loads(row['old_payload']) if isinstance(row['old_payload'], str) else row['old_payload']
            new_payload = json.loads(row['new_payload']) if isinstance(row['new_payload'], str) else row['new_payload']

            # --- Chain Verification Logic ---
            if verify_chain:
                # The first entry for THIS record might not be the first in the whole ledger.
                # So we only check against genesis hash if its prev_hash is indeed the genesis hash.
                # Otherwise, we just trust the first one and start the chain from there.
                if is_first_record_in_timeline:
                    expected_prev_hash = row['prev_hash']
                    is_first_record_in_timeline = False

                current_prev_hash = row['prev_hash']
                if current_prev_hash != expected_prev_hash:
                    chain_is_valid = False
                    status_icon = "[bold red]✗ BROKEN[/bold red]"
                    console.print(f"  [red]Chain break detected at tx_order {row['tx_order']}![/red]")
                    console.print(f"    - Expected prev_hash: {expected_prev_hash}")
                    console.print(f"    - Found prev_hash:    {current_prev_hash}")
                else:
                    status_icon = "[green]✓[/green]"
                
                expected_prev_hash = row['chain_hash']
            else:
                status_icon = ""

            # --- Human-Readable Output ---
            op_style = {
                'INSERT': Style(color="green", bold=True),
                'UPDATE': Style(color="blue", bold=True),
                'DELETE': Style(color="red", bold=True)
            }.get(op_type, Style())

            diff_str = format_payload_diff(op_type, old_payload, new_payload)
            console.print(f"{status_icon} [dim]{created_at}[/dim] ", style=op_style, end="")
            console.print(f"{op_type:<7} ", style=op_style, end="")
            console.print(diff_str)

        if verify_chain:
            if chain_is_valid:
                console.print("\n[bold green]✅ Chain continuity verified for this record's timeline.[/bold green]")
            else:
                console.print("\n[bold red]❌ Tampering detected: Hash chain is broken.[/bold red]")

    finally:
        if conn and conn.is_connected():
            conn.close()