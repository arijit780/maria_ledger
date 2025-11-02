from maria_ledger.db.connection import get_connection
from maria_ledger.utils.config import get_config
from maria_ledger.utils.keys import public_key_fingerprint_from_file, load_private_key
from maria_ledger.crypto.signer import sign_merkle_root
from typing import Optional, Tuple, List
from maria_ledger.crypto.merkle_tree import MerkleTree
from datetime import datetime
import json


def get_latest_merkle_root(table_name: str) -> Optional[Tuple[str, datetime, Optional[List[str]]]]:
    """
    Fetch the latest Merkle root, timestamp, and fields_to_hash for a given ledger table.
    
    Args:
        table_name: The name of the ledger table
        
    Returns:
        Tuple of (merkle_root, timestamp, fields_to_hash) or None if no root exists.
        fields_to_hash may be None for backward compatibility (use all fields).
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if fields_to_hash column exists (for backward compatibility)
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'ledger_roots' 
            AND COLUMN_NAME = 'fields_to_hash'
        """)
        has_fields_to_hash = cursor.fetchone() is not None
        
        if has_fields_to_hash:
            cursor.execute("""
                SELECT root_hash, computed_at, fields_to_hash 
                FROM ledger_roots 
                WHERE table_name = %s 
                ORDER BY computed_at DESC 
                LIMIT 1
            """, (table_name,))
        else:
            cursor.execute("""
                SELECT root_hash, computed_at 
                FROM ledger_roots 
                WHERE table_name = %s 
                ORDER BY computed_at DESC 
                LIMIT 1
            """, (table_name,))
        
        result = cursor.fetchone()
        if result:
            # Parse fields_to_hash from JSON if present, otherwise None (backward compatible)
            fields_to_hash = None
            if has_fields_to_hash and result.get('fields_to_hash'):
                try:
                    fields_to_hash = json.loads(result['fields_to_hash'])
                except (json.JSONDecodeError, TypeError):
                    fields_to_hash = None
            return result['root_hash'], result['computed_at'], fields_to_hash
        return None
        
    finally:
        cursor.close()
        conn.close()

def compute_root_from_chain_hashes(conn, table_name: str) -> Optional[str]:
    """
    Computes a Merkle root directly from the `chain_hash` values in the ledger.
    This is more efficient than state reconstruction and verifies the entire history.
    """
    cursor = conn.cursor()
    try:
        # Fetch all chain_hash values in their exact order.
        cursor.execute(
            "SELECT chain_hash FROM ledger WHERE table_name = %s ORDER BY tx_order ASC",
            (table_name,)
        )
        # The result is a list of tuples, e.g., [('hash1',), ('hash2',)]
        hashes = [row[0] for row in cursor.fetchall() if row[0] is not None]
        
        if not hashes:
            return None
        return MerkleTree(hashes).get_root()
    finally:
        cursor.close()

def compute_and_store_merkle_root(table_name: str, fields_to_hash: Optional[List[str]] = None) -> str:
    """
    Compute and store a new Merkle root for the given table.
    
    Args:
        table_name: Name of the table to compute root for
        fields_to_hash: Optional list of fields to use for hash computation. 
                       Stored for future verification use. If None, all fields are used.
    
    Returns:
        The computed Merkle root hash
    """
    cfg = get_config()
    conn = get_connection()

    try:
        # Phase 3 Change: Compute root from the ledger's chain_hash values.
        root = compute_root_from_chain_hashes(conn, table_name)
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

    # Store in ledger_roots with signature and fields_to_hash
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Check if fields_to_hash column exists (for backward compatibility)
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'ledger_roots' 
            AND COLUMN_NAME = 'fields_to_hash'
        """)
        has_fields_to_hash_column = cursor.fetchone() is not None
        
        if has_fields_to_hash_column:
            # Store fields_to_hash as JSON (null if not specified)
            fields_to_hash_json = json.dumps(fields_to_hash) if fields_to_hash else None
            cursor.execute(
                """
                INSERT INTO ledger_roots(
                    table_name, root_hash, signer, signature, pubkey_fingerprint, fields_to_hash
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (table_name, root, signer_id, signature_b64, pub_fingerprint, fields_to_hash_json)
            )
        else:
            # Backward compatible: insert without fields_to_hash column
            cursor.execute(
                """
                INSERT INTO ledger_roots(
                    table_name, root_hash, signer, signature, pubkey_fingerprint
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (table_name, root, signer_id, signature_b64, pub_fingerprint)
            )
        conn.commit()
        
        print(f"[✓] Merkle root stored and signed: {root} (signer={signer_id})")
        return root
        
    finally:
        cursor.close()
        conn.close()