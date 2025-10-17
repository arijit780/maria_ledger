from maria_ledger.db.connection import get_connection
from maria_ledger.db.merkle_service import verify_table_with_merkle_root, compute_and_store_merkle_root
from maria_ledger.utils.config import get_config
from maria_ledger.crypto.signer import verify_merkle_root_signature
from maria_ledger.utils.keys import public_key_fingerprint_from_file
from maria_ledger.utils.logger import get_logger
import typer
import json

logger = get_logger("cli-verify")

def verify_table_command(
    table: str,
    public_key: str = typer.Option(None, "--public-key", help="Optional: Path to RSA public key"),
    json_output: bool = typer.Option(False, "--json", help="Output result in JSON format"),
    force: bool = typer.Option(False, "--force", "-f", help="Force recompute Merkle root regardless of existing root")
):
    """Verify table integrity using hash chain and Merkle root."""
    cfg = get_config()
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT root_hash, signature, signer, pubkey_fingerprint, computed_at
        FROM ledger_roots
        WHERE table_name=%s
        ORDER BY computed_at DESC
        LIMIT 1
    """, (table,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row or force:
        if force:
            typer.echo(f"[i] Force recomputing Merkle root for table {table}...")
        else:
            typer.echo(f"[i] No Merkle root stored for table {table}. Computing now...")
        new_root = compute_and_store_merkle_root(table)
        typer.echo(f"[✓] {'Updated' if force else 'Stored initial'} Merkle root: {new_root}")
        return

    root = row["root_hash"]
    signature_b64 = row["signature"]
    signer = row["signer"]
    fingerprint = row["pubkey_fingerprint"]

    # 1) Verify the Merkle root matches current computed root
    ok_root = verify_table_with_merkle_root(table, root)

    # 2) Verify the signature using the configured public key path
    # Use provided public key or fall back to config
    pub_path = public_key or cfg["crypto"].get("public_key_path")
    if not pub_path:
        logger.error("No public key provided and none configured")
        return

    actual_fp = public_key_fingerprint_from_file(pub_path)
    if actual_fp != fingerprint:
        logger.warning(f"Public key mismatch: local fingerprint {actual_fp} != stored {fingerprint}")
        sig_ok = False
    else:
        sig_ok = verify_merkle_root_signature(pub_path, root, signature_b64)

    typer.echo(f"[•] Latest recorded root: {root} (signed by {signer} at {row['computed_at']})")
    typer.echo(f"[✓] Merkle root integrity: {'OK' if ok_root else 'MISMATCH'}")
    typer.echo(f"[✓] Signature verification: {'OK' if sig_ok else 'FAILED'}")

    result = {
        "table": table,
        "merkle_root": root,
        "signature_valid": sig_ok,
        "root_valid": ok_root,
        "signer": signer,
        "timestamp": row["computed_at"].isoformat(),
        "public_key_fingerprint": fingerprint,
        "status": "passed" if (ok_root and sig_ok) else "failed"
    }

    if json_output:
        typer.echo(json.dumps(result, indent=2))
    else:
        if not ok_root or not sig_ok:
            typer.echo("[✗] Integrity check failed! Investigate immediately.")
        else:
            typer.echo("[✓] Table verification passed (root + signature).")

