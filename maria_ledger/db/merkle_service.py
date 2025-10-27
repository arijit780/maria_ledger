from maria_ledger.db.connection import get_connection
from maria_ledger.utils.config import get_config
from maria_ledger.utils.keys import public_key_fingerprint_from_file, load_private_key
from maria_ledger.crypto.signer import sign_merkle_root
from maria_ledger.cli.reconstruct import reconstruct_table_state
from typing import Optional, Tuple
from datetime import datetime


def get_latest_merkle_root(table_name: str) -> Optional[Tuple[str, datetime]]:
    """
    Fetch the latest Merkle root and timestamp for a given ledger table.
    
    Args:
        table_name: The name of the ledger table
        
    Returns:
        Tuple of (merkle_root, timestamp) or None if no root exists
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT root_hash, computed_at 
            FROM ledger_roots 
            WHERE table_name = %s 
            ORDER BY computed_at DESC 
            LIMIT 1
        """, (table_name,))
        
        result = cursor.fetchone()
        if result:
            return result['root_hash'], result['computed_at']
        return None
        
    finally:
        cursor.close()
        conn.close()

def compute_and_store_merkle_root(table_name: str, reference_table: str = None) -> str:
    """
    Compute and store a new Merkle root for the given table.
    
    Args:
        table_name: Name of the table to compute root for
        reference_table: Optional name of another ledger table to cross-reference
    
    Returns:
        The computed Merkle root hash
    """
    cfg = get_config()
    conn = get_connection()

    try:
        # Re-use the robust reconstruction logic to get the state and root
        state, root = reconstruct_table_state(conn, table_name)
    finally:
        conn.close()

    if not root:
        print(f"[!] Could not compute Merkle root for table {table_name}. It might be empty.")
        return None

    # Sign the root
    priv_path = cfg["crypto"]["private_key_path"]
    signer_id = cfg["crypto"].get("signer_id", "maria-ledger")
    signature_b64 = sign_merkle_root(priv_path, root)

    # fingerprint of public key
    pub_path = cfg["crypto"]["public_key_path"]
    pub_fingerprint = public_key_fingerprint_from_file(pub_path)

    # Get reference root if specified
    reference_root = None
    if reference_table:
        ref_root = get_latest_merkle_root(reference_table)
        if ref_root:
            reference_root = ref_root[0]

    # Store in ledger_roots with signature and optional reference
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO ledger_roots(
                table_name, root_hash, reference_root, reference_table,
                signer, signature, pubkey_fingerprint
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (table_name, root, reference_root, reference_table,
             signer_id, signature_b64, pub_fingerprint)
        )
        conn.commit()
        
        print(f"[✓] Merkle root stored and signed: {root} (signer={signer_id})")
        if reference_table and reference_root:
            print(f"[✓] Cross-referenced with {reference_table}")
        return root
        
    finally:
        cursor.close()
        conn.close()
