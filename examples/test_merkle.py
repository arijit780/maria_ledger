from maria_ledger.db.connection import get_connection
from maria_ledger.db.merkle_service import verify_table_with_merkle_root

TABLE = "ledger_customers"

# Fetch the last stored Merkle root before the tampering
conn = get_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute(
    "SELECT root_hash, computed_at FROM ledger_roots WHERE table_name=%s ORDER BY computed_at DESC LIMIT 1",
    (TABLE,)
)
row = cursor.fetchone()
cursor.close()
conn.close()

if row:
    last_root = row['root_hash']
    # Verify against current table
    verify_table_with_merkle_root(TABLE, last_root)
