from maria_ledger.db.connection import get_connection
from maria_ledger.crypto.merkle_tree import MerkleTree

def compute_and_store_merkle_root(table_name: str) -> str:
    """
    Compute Merkle root from all row_hashes of table_name
    and store it in ledger_roots table.
    Returns the root hash.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Get all row hashes in order
    cursor.execute(f"SELECT row_hash FROM {table_name} ORDER BY valid_from ASC")
    hashes = [row['row_hash'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    if not hashes:
        print(f"[!] Table {table_name} has no rows")
        return None

    # Build Merkle Tree
    tree = MerkleTree(hashes)
    root = tree.get_root()

    # Store in ledger_roots
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ledger_roots(table_name, root_hash) VALUES (%s, %s)",
        (table_name, root)
    )
    conn.commit()
    cursor.close()
    conn.close()

    print(f"[✓] Merkle root for table {table_name} stored: {root}")
    return root

def verify_table_with_merkle_root(table_name: str, root_hash: str) -> bool:
    """
    Recompute Merkle root from table and compare with stored root.
    Returns True if matches.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT row_hash FROM {table_name} ORDER BY valid_from ASC")
    hashes = [row['row_hash'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    tree = MerkleTree(hashes)
    computed_root = tree.get_root()
    if computed_root == root_hash:
        print(f"[✓] Table {table_name} matches Merkle root {root_hash}")
        return True
    else:
        print(f"[!] Table {table_name} root mismatch!")
        print(f"    Expected: {root_hash}")
        print(f"    Computed: {computed_root}")
        return False
