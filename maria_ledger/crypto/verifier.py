from maria_ledger.crypto.hash_chain import compute_row_hash
from maria_ledger.db.connection import get_connection

def verify_table_chain(table_name: str) -> bool:
    """
    Recompute hashes for all versions in table and validate continuity.
    Returns True if chain is intact.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(f"SELECT * FROM {table_name} ORDER BY valid_from ASC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        print(f"[!] No rows found in {table_name}")
        return False

    prev_hash = "0" * 64
    for idx, row in enumerate(rows):
        data_subset = {
            k: v for k, v in row.items()
            if k not in ("row_hash", "prev_hash")
        }
        expected_hash = compute_row_hash(data_subset, prev_hash)
        if expected_hash != row["row_hash"]:
            print(f"[❌] Hash mismatch at row {idx+1}: expected {expected_hash}, found {row['row_hash']}")
            return False
        prev_hash = row["row_hash"]

    print(f"[✅] Chain intact for {table_name} ({len(rows)} rows verified)")
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m maria_ledger.crypto.verifier <table_name>")
        sys.exit(1)

    table = sys.argv[1]
    verify_table_chain(table)
