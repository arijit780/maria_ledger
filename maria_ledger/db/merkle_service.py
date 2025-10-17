from maria_ledger.db.connection import get_connection
from maria_ledger.crypto.merkle_tree import MerkleTree
from maria_ledger.utils.config import get_config
from maria_ledger.utils.keys import public_key_fingerprint_from_file, load_private_key
from maria_ledger.crypto.signer import sign_merkle_root
import base64, os


def compute_and_store_merkle_root(table_name: str) -> str:
    cfg = get_config()
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT row_hash FROM {table_name} ORDER BY valid_from ASC")
    hashes = [row['row_hash'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    if not hashes:
        print(f"[!] Table {table_name} has no rows")
        return None

    tree = MerkleTree(hashes)
    root = tree.get_root()

    # Sign the root
    priv_path = cfg["crypto"]["private_key_path"]
    signer_id = cfg["crypto"].get("signer_id", "maria-ledger")
    signature_b64 = sign_merkle_root(priv_path, root)

    # fingerprint of public key
    pub_path = cfg["crypto"]["public_key_path"]
    pub_fingerprint = public_key_fingerprint_from_file(pub_path)

    # Store in ledger_roots with signature and signer info
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ledger_roots(table_name, root_hash, signer, signature, pubkey_fingerprint) VALUES (%s, %s, %s, %s, %s)",
        (table_name, root, signer_id, signature_b64, pub_fingerprint)
    )
    conn.commit()
    cursor.close()
    conn.close()

    print(f"[✓] Merkle root stored and signed: {root} (signer={signer_id})")
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
