import typer
import datetime
from maria_ledger.db.connection import get_connection
from maria_ledger.db.merkle_service import verify_table_with_merkle_root, compute_and_store_merkle_root
from maria_ledger.utils.logger import get_logger
from maria_ledger.utils.config import get_alert_config
from maria_ledger.utils.formatter import pretty_time
from maria_ledger.utils.alerts import send_alert

app = typer.Typer()
logger = get_logger("audit")

@app.command()
def run(interval_hours: int = typer.Option(24, "--interval", help="Hours between audits")):
    """
    Periodic integrity audit.
    Recomputes and validates Merkle roots for all ledger tables.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Find all tables with a ledger structure
    cursor.execute("""
        SELECT TABLE_NAME
        FROM information_schema.tables
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME LIKE 'ledger_%'
          AND TABLE_NAME != 'ledger_roots'
    """)
    tables = [row["TABLE_NAME"] for row in cursor.fetchall()]
    logger.info(f"Found {len(tables)} ledger tables.")

    issues = []

    for table in tables:
        cursor.execute("""
            SELECT root_hash
            FROM ledger_roots
            WHERE table_name=%s
            ORDER BY computed_at DESC
            LIMIT 1
        """, (table,))
        row = cursor.fetchone()
        stored_root = row["root_hash"] if row else None

        if not stored_root:
            logger.info(f"No stored root for {table}, computing initial checkpoint.")
            compute_and_store_merkle_root(table)
            continue

        ok = verify_table_with_merkle_root(table, stored_root)
        if ok:
            logger.info(f"[✓] {table} integrity verified.")
        else:
            logger.error(f"[✗] Tamper detected in {table}!")
            issues.append(table)

    cursor.close()
    conn.close()

    if issues:
        msg = f"Integrity issues detected in: {', '.join(issues)}"
        send_alert("MariaLedger Integrity Alert", msg)
        typer.echo(f"[!] {msg}")
    else:
        typer.echo("[✓] All ledger tables verified successfully.")

    logger.info(f"Audit completed at {pretty_time(datetime.datetime.utcnow())}")
