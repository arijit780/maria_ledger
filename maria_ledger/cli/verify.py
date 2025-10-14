from maria_ledger.db.connection import get_connection
from maria_ledger.db.merkle_service import verify_table_with_merkle_root
from maria_ledger.utils.config import get_config
from maria_ledger.crypto.signing import verify_signature
from maria_ledger.utils.keys import public_key_fingerprint_from_file
import typer

def verify_table_command(table: str):
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

    if not row:
        typer.echo(f"[i] No Merkle root stored for table {table}. Computing now...")
        new_root = compute_and_store_merkle_root(table)
        typer.echo(f"[✓] Stored initial Merkle root: {new_root}")
        return

    root = row["root_hash"]
    signature_b64 = row["signature"]
    signer = row["signer"]
    fingerprint = row["pubkey_fingerprint"]

    # 1) Verify the Merkle root matches current computed root
    ok_root = verify_table_with_merkle_root(table, root)

    # 2) Verify the signature using the configured public key path
    pub_path = cfg["crypto"]["public_key_path"]
    actual_fp = public_key_fingerprint_from_file(pub_path)
    if actual_fp != fingerprint:
        typer.echo(f"[!] Public key mismatch: local public key fingerprint {actual_fp} != stored {fingerprint}")
        sig_ok = False
    else:
        sig_ok = verify_signature(pub_path, root, signature_b64)

    typer.echo(f"[•] Latest recorded root: {root} (signed by {signer} at {row['computed_at']})")
    typer.echo(f"[✓] Merkle root integrity: {'OK' if ok_root else 'MISMATCH'}")
    typer.echo(f"[✓] Signature verification: {'OK' if sig_ok else 'FAILED'}")

    if not ok_root or not sig_ok:
        typer.echo("[✗] Integrity check failed! Investigate immediately.")
    else:
        typer.echo("[✓] Table verification passed (root + signature).")

