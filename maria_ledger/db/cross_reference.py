"""Cross-ledger trust utility functions for Maria-Ledger."""

from maria_ledger.db.connection import get_connection
from maria_ledger.db.merkle_service import get_latest_merkle_root
from maria_ledger.utils.logger import get_logger

logger = get_logger("cross-reference")

def record_cross_reference(source_ledger: str, target_ledger: str) -> bool:
    """
    Record cross-reference between two ledgers by storing each other's latest Merkle roots.
    
    Args:
        source_ledger: The name of the source ledger table
        target_ledger: The name of the target ledger table to reference
        
    Returns:
        True if cross-reference was recorded successfully
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get latest roots for both ledgers
        source_root = get_latest_merkle_root(source_ledger)
        target_root = get_latest_merkle_root(target_ledger)
        
        if not source_root or not target_root:
            logger.error(f"Missing Merkle root for {'source' if not source_root else 'target'} ledger")
            return False
        
        # Record cross-references in both directions
        cursor.execute("""
            INSERT INTO ledger_roots 
            (table_name, root_hash, reference_root, reference_table, computed_at)
            VALUES (%s, %s, %s, %s, NOW(6))
        """, (
            source_ledger, source_root[0], target_root[0], target_ledger
        ))
        
        cursor.execute("""
            INSERT INTO ledger_roots 
            (table_name, root_hash, reference_root, reference_table, computed_at)
            VALUES (%s, %s, %s, %s, NOW(6))
        """, (
            target_ledger, target_root[0], source_root[0], source_ledger
        ))
        
        conn.commit()
        logger.info(f"Recorded cross-reference between {source_ledger} and {target_ledger}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to record cross-reference: {e}")
        conn.rollback()
        return False
        
    finally:
        cursor.close()
        conn.close()

def verify_cross_reference(source_ledger: str, target_ledger: str) -> dict:
    """
    Verify the cross-reference integrity between two ledgers.
    
    Args:
        source_ledger: The name of the source ledger table
        target_ledger: The name of the target ledger table
        
    Returns:
        Dict containing verification results and details
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get latest cross-reference entries for both ledgers
        cursor.execute("""
            SELECT table_name, root_hash, reference_root, reference_table, computed_at
            FROM ledger_roots
            WHERE (table_name = %s AND reference_table = %s)
               OR (table_name = %s AND reference_table = %s)
            ORDER BY computed_at DESC
            LIMIT 2
        """, (source_ledger, target_ledger, target_ledger, source_ledger))
        
        refs = cursor.fetchall()
        
        # Get current Merkle roots
        source_current = get_latest_merkle_root(source_ledger)
        target_current = get_latest_merkle_root(target_ledger)
        
        results = {
            "source_ledger": source_ledger,
            "target_ledger": target_ledger,
            "source_current_root": source_current[0] if source_current else None,
            "target_current_root": target_current[0] if target_current else None,
            "cross_refs_valid": False,
            "errors": [],
            "last_verified": None
        }
        
        if len(refs) != 2:
            results["errors"].append("Missing cross-reference entries")
            return results
            
        # Verify bidirectional references match
        source_ref = next(r for r in refs if r["table_name"] == source_ledger)
        target_ref = next(r for r in refs if r["table_name"] == target_ledger)
        
        if source_ref["reference_root"] != target_ref["root_hash"]:
            results["errors"].append(
                f"Source reference ({source_ref['reference_root']}) != Target root ({target_ref['root_hash']})"
            )
            
        if target_ref["reference_root"] != source_ref["root_hash"]:
            results["errors"].append(
                f"Target reference ({target_ref['reference_root']}) != Source root ({source_ref['root_hash']})"
            )
        
        results["cross_refs_valid"] = len(results["errors"]) == 0
        results["last_verified"] = max(r["computed_at"] for r in refs)
        
        return results
        
    finally:
        cursor.close()
        conn.close()