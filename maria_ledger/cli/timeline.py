"""
timeline.py

CLI command to replay the full audit history of a single record or table.
Supports time-range filtering and diff mode.
"""

import typer
import json
from rich.console import Console
from rich.style import Style
from typing import Optional, Dict, Any, List

from maria_ledger.db.connection import get_connection
from maria_ledger.utils.helpers import json_serial
from maria_ledger.cli.reconstruct import (
    reconstruct_table_state,
    load_ledger_stream,
    apply_ops_to_state,
    _parse_payload,
)
from maria_ledger.crypto.hash_utils import compute_record_hash

console = Console()


# ============================================================
# === Payload Difference Formatting ==========================
# ============================================================

def format_payload_diff(op_type: str, old_payload: dict, new_payload: dict) -> str:
    """Creates a human-readable summary of what changed in a transaction."""
    if op_type == "INSERT":
        return ", ".join(
            f"[green]{k}[/green]=[yellow]{v}[/yellow]"
            for k, v in (new_payload or {}).items()
        )
    if op_type == "DELETE":
        return ", ".join(
            f"[red]{k}[/red]=[yellow]{v}[/yellow]"
            for k, v in (old_payload or {}).items()
        )

    if op_type == "UPDATE":
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


# ============================================================
# === State Reconstruction Helpers ===========================
# ============================================================

def load_ledger_stream_up_to_tx(conn, table_name: str, max_tx_order: int, record_id: Optional[str] = None):
    """Load ledger stream up to a specific tx_order."""
    sql = (
        "SELECT tx_order, record_id, op_type, old_payload, new_payload "
        "FROM ledger WHERE table_name = %s AND tx_order <= %s"
    )
    params = [table_name, max_tx_order]
    if record_id:
        sql += " AND record_id = %s"
        params.append(record_id)
    sql += " ORDER BY tx_order ASC"

    with conn.cursor(dictionary=True, buffered=False) as cur:
        cur.execute(sql, params)
        for row in cur:
            yield (
                row["tx_order"],
                row["record_id"],
                row["op_type"],
                row["old_payload"],
                row["new_payload"],
            )


def reconstruct_state_up_to_tx(
    conn, table_name: str, max_tx_order: int, record_id: Optional[str] = None
) -> Dict[str, Any]:
    """Reconstruct table state up to a specific tx_order."""
    ledger_stream = load_ledger_stream_up_to_tx(conn, table_name, max_tx_order, record_id)
    return apply_ops_to_state(ledger_stream)


# ============================================================
# === State Comparison =======================================
# ============================================================

def compare_states(from_state: Dict[str, Any], to_state: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two states and return diff information."""
    from_ids = set(from_state.keys())
    to_ids = set(to_state.keys())

    inserted = sorted(to_ids - from_ids, key=lambda x: int(x) if x.isdigit() else x)
    deleted = sorted(from_ids - to_ids, key=lambda x: int(x) if x.isdigit() else x)
    modified = []

    # Find modified records (same ID but different hash)
    common_ids = sorted(from_ids & to_ids, key=lambda x: int(x) if x.isdigit() else x)
    for record_id in common_ids:
        from_hash = compute_record_hash(record_id, from_state[record_id])
        to_hash = compute_record_hash(record_id, to_state[record_id])
        if from_hash != to_hash:
            modified.append(record_id)

    # Calculate affected range
    numeric_changed_ids = [int(rid) for rid in inserted + deleted + modified if rid.isdigit()]
    all_changed_ids = sorted(numeric_changed_ids) if numeric_changed_ids else []
    affected_range = None
    if all_changed_ids:
        affected_range = f"IDs {min(all_changed_ids)}-{max(all_changed_ids)}"

    return {
        "inserted": inserted,
        "deleted": deleted,
        "modified": modified,
        "affected_range": affected_range,
        "from_state": from_state,
        "to_state": to_state,
    }


# ============================================================
# === Timeline Command =======================================
# ============================================================

def timeline_command(
    table_name: str = typer.Argument(..., help="The logical table name (e.g., 'customers')."),
    record_id: Optional[str] = typer.Option(None, "--id", help="The ID of the record to trace."),
    from_tx: Optional[int] = typer.Option(None, "--from-tx", help="Starting tx_order (inclusive)."),
    to_tx: Optional[int] = typer.Option(None, "--to-tx", help="Ending tx_order (inclusive)."),
    verify_chain: bool = typer.Option(False, "--verify-chain", help="Validate hash chain continuity during replay."),
    json_output: bool = typer.Option(False, "--json", help="Output the timeline as a JSON array."),
):
    """
    Display the chronological audit history (timeline) for records.

    Command Modes & Methodology:
    1. SINGLE RECORD TIMELINE: timeline customers --id 3
       → Shows all transactions for record 3

    2. TABLE-WIDE TIMELINE: timeline customers
       → Shows all transactions across all records

    3. TIME RANGE FILTER: timeline customers --from-tx 10 --to-tx 25
       → Shows transactions between tx_order 10 and 25

    4. DIFF MODE: timeline customers --from-tx 10 --to-tx 25
       → Compares state at tx_order 10 vs 25

    5. CHAIN VERIFICATION: timeline customers --id 3 --verify-chain
       → Checks hash chain continuity for a specific record
    """
    conn = get_connection()

    # ------------------------------------------------------------
    # Diff mode: Compare two snapshots
    # ------------------------------------------------------------
    if from_tx is not None and to_tx is not None:
        try:
            console.print(f"Diff between tx_order {from_tx} and {to_tx} for [cyan]{table_name}[/]:")

            from_state = reconstruct_state_up_to_tx(conn, table_name, from_tx, record_id)
            to_state = reconstruct_state_up_to_tx(conn, table_name, to_tx, record_id)
            diff = compare_states(from_state, to_state)

            changed_records = sorted(
                diff["modified"] + diff["inserted"] + diff["deleted"],
                key=lambda x: int(x) if x.isdigit() else x,
            )

            if not changed_records:
                console.print("[green]No changes detected.[/green]")
                return

            console.print(f"\n[bold]Changed records:[/bold] {changed_records}")
            if diff["affected_range"]:
                console.print(f"[bold]Affected range:[/bold] {diff['affected_range']}")

            # Detailed changes
            console.print("\n[bold]Detailed changes:[/bold]")
            for record_id in diff["modified"]:
                console.print(f"\n[cyan]Record {record_id}:[/cyan]")
                diff_str = format_payload_diff("UPDATE", diff["from_state"][record_id], diff["to_state"][record_id])
                console.print(f" [blue]UPDATE[/blue] {diff_str}")

            for record_id in diff["inserted"]:
                console.print(f"\n[cyan]Record {record_id}:[/cyan]")
                diff_str = format_payload_diff("INSERT", None, diff["to_state"][record_id])
                console.print(f" [green]INSERT[/green] {diff_str}")

            for record_id in diff["deleted"]:
                console.print(f"\n[cyan]Record {record_id}:[/cyan]")
                diff_str = format_payload_diff("DELETE", diff["from_state"][record_id], None)
                console.print(f" [red]DELETE[/red] {diff_str}")

        finally:
            if conn and conn.is_connected():
                conn.close()
        return

    # ------------------------------------------------------------
    # Regular timeline mode
    # ------------------------------------------------------------
    try:
        sql = """
        SELECT tx_order, op_type, old_payload, new_payload, created_at, prev_hash, chain_hash, record_id
        FROM ledger
        WHERE table_name = %s
        """
        params = [table_name]

        if record_id:
            sql += " AND record_id = %s"
            params.append(record_id)
        if from_tx is not None:
            sql += " AND tx_order >= %s"
            params.append(from_tx)
        if to_tx is not None:
            sql += " AND tx_order <= %s"
            params.append(to_tx)

        sql += " ORDER BY tx_order ASC"

        with conn.cursor(dictionary=True) as cur:
            cur.execute(sql, params)
            history = cur.fetchall()

        if not history:
            msg = f"No history found for table '{table_name}'"
            if record_id:
                msg += f" with record ID '{record_id}'"
            console.print(f"[yellow]{msg}.[/yellow]")
            return

        if json_output:
            print(json.dumps(history, default=json_serial, sort_keys=True, separators=(",", ":")))
            return

        # Human-readable timeline
        header = (
            f"Timeline for [cyan]{table_name}[/] ID [bold]{record_id}[/bold]:"
            if record_id
            else f"Timeline for [cyan]{table_name}[/] (table-wide):"
        )
        console.print(header)

        if from_tx is not None or to_tx is not None:
            range_str = []
            if from_tx is not None:
                range_str.append(f"from tx_order {from_tx}")
            if to_tx is not None:
                range_str.append(f"to tx_order {to_tx}")
            console.print(f"[dim]Filtered: {' and '.join(range_str)}[/dim]")

        expected_prev_hash = "0" * 64
        is_first_record_in_timeline = True
        chain_is_valid = True

        for row in history:
            op_type = row["op_type"]
            created_at = row["created_at"].isoformat()

            old_payload = json.loads(row["old_payload"]) if isinstance(row["old_payload"], str) else row["old_payload"]
            new_payload = json.loads(row["new_payload"]) if isinstance(row["new_payload"], str) else row["new_payload"]

            # --- Chain Verification ---
            if verify_chain:
                if is_first_record_in_timeline:
                    expected_prev_hash = row["prev_hash"]
                    is_first_record_in_timeline = False

                current_prev_hash = row["prev_hash"]
                if current_prev_hash != expected_prev_hash:
                    chain_is_valid = False
                    status_icon = "[bold red]✗ BROKEN[/bold red]"
                    console.print(f" [red]Chain break detected at tx_order {row['tx_order']}![/red]")
                    console.print(f" - Expected prev_hash: {expected_prev_hash}")
                    console.print(f" - Found prev_hash: {current_prev_hash}")
                else:
                    status_icon = "[green]✓[/green]"
                    expected_prev_hash = row["chain_hash"]
            else:
                status_icon = ""

            # --- Pretty Output ---
            op_style = {
                "INSERT": Style(color="green", bold=True),
                "UPDATE": Style(color="blue", bold=True),
                "DELETE": Style(color="red", bold=True),
            }.get(op_type, Style())

            diff_str = format_payload_diff(op_type, old_payload, new_payload)
            record_info = f"ID {row['record_id']}: " if not record_id else ""

            console.print(f"{status_icon} [dim]{created_at}[/dim] ", style=op_style, end="")
            console.print(f"{op_type:<7} ", style=op_style, end="")
            if record_info:
                console.print(f"[cyan]{record_info}[/cyan]", end="")
            console.print(diff_str)

        if verify_chain:
            if chain_is_valid:
                console.print("\n[bold green]✅ Chain continuity verified for this record's timeline.[/bold green]")
            else:
                console.print("\n[bold red]❌ Tampering detected: Hash chain is broken.[/bold red]")

    finally:
        if conn and conn.is_connected():
            conn.close()
