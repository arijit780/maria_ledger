"""
hash_utils.py

Centralized hashing utilities for Maria Ledger.
Ensures consistent hashing algorithms and canonicalization across all modules.
"""

import hashlib
import json
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union


# ============================================================
# === Canonicalization Utilities =============================
# ============================================================

def canonicalize_datetime(dt: Union[datetime, date]) -> str:
    """
    Canonical datetime formatting used across all Maria Ledger modules.

    Format: YYYY-MM-DD HH:MM:SS.ffffff
    This matches the SQL DATE_FORMAT('%Y-%m-%d %H:%i:%s.%f') format.
    """
    if isinstance(dt, date) and not isinstance(dt, datetime):
        # Convert date to datetime at midnight
        dt = datetime.combine(dt, datetime.min.time())
    return dt.strftime('%Y-%m-%d %H:%M:%S.%f')


def canonicalize_json(obj: Any) -> str:
    """
    Canonical JSON serialization used across all Maria Ledger modules.

    Features:
        - Sorted keys for deterministic output
        - Compact separators (no spaces)
        - Consistent datetime formatting
        - UTF-8 encoding
    """
    def json_serializer(o):
        if isinstance(o, (datetime, date)):
            return canonicalize_datetime(o)
        raise TypeError(f"Type {type(o)} not serializable")

    return json.dumps(
        obj,
        separators=(',', ':'),
        sort_keys=True,
        default=json_serializer,
        ensure_ascii=False
    )


# ============================================================
# === Hashing Algorithms =====================================
# ============================================================

def compute_row_hash(row_dict: Dict[str, Any], prev_hash: str) -> str:
    """
    Compute SHA256 hash of row contents + prev_hash.
    This is the standard row hashing algorithm used in hash chains.

    Format:
        JSON(canonical_dict) + prev_hash

    Args:
        row_dict: Dictionary containing row data
        prev_hash: Previous hash in the chain (64 hex chars)

    Returns:
        64-character hex string (SHA256 hash)
    """
    canonical = canonicalize_json(row_dict)
    data = canonical + prev_hash
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_chain_hash(
    prev_hash: str,
    tx_id: str,
    record_id: str,
    op_type: str,
    old_payload: Optional[Dict[str, Any]],
    new_payload: Optional[Dict[str, Any]],
    created_at: datetime
) -> str:
    """
    Compute chain hash for ledger entries.
    Matches SQL trigger implementation:

    SHA2(CONCAT_WS('|', prev_hash, tx_id, record_id, op_type, old_payload, new_payload, created_at), 256)

    Args:
        prev_hash: Previous hash in the chain
        tx_id: Transaction ID
        record_id: Record ID
        op_type: Operation type (INSERT, UPDATE, DELETE)
        old_payload: Old payload data (None for INSERT)
        new_payload: New payload data (None for DELETE)
        created_at: Creation timestamp

    Returns:
        64-character hex string (SHA256 hash)
    """
    # Canonicalize payloads
    old_payload_str = canonicalize_json(old_payload) if old_payload is not None else 'NULL'
    new_payload_str = canonicalize_json(new_payload) if new_payload is not None else 'NULL'
    created_at_str = canonicalize_datetime(created_at)

    # Build data string matching SQL CONCAT_WS('|', ...)
    data_to_hash = '|'.join([
        prev_hash,
        tx_id,
        record_id,
        op_type,
        old_payload_str,
        new_payload_str,
        created_at_str
    ])
    return hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()


def compute_record_hash(
    record_id: str,
    payload: Dict[str, Any],
    fields_to_hash: Optional[List[str]] = None
) -> str:
    """
    Compute hash for a record in reconstruction/verification.

    Format:
        record_id + '|' + canonicalize_json(payload)

    Args:
        record_id: Record identifier
        payload: Record payload data
        fields_to_hash: Optional list of fields to include in hash

    Returns:
        64-character hex string (SHA256 hash)
    """
    if fields_to_hash:
        # Filter payload to include only specified fields
        filtered_payload = {k: payload.get(k) for k in sorted(fields_to_hash)}
        payload_to_hash = filtered_payload
    else:
        payload_to_hash = payload

    canonical_payload = canonicalize_json(payload_to_hash)
    data = f"{record_id}|{canonical_payload}"
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def compute_merkle_hash(left_hash: str, right_hash: str) -> str:
    """
    Compute Merkle tree node hash.

    Format:
        left_hash + right_hash

    Args:
        left_hash: Left child hash
        right_hash: Right child hash

    Returns:
        64-character hex string (SHA256 hash)
    """
    return hashlib.sha256((left_hash + right_hash).encode('utf-8')).hexdigest()


# # ============================================================
# # === Consistency Self-Test ==================================
# # ============================================================

# def verify_hash_consistency() -> Dict[str, bool]:
#     """
#     Verify that all hashing functions produce consistent results.

#     Returns:
#         Dictionary with test results for each hashing function.
#     """
#     test_data = {
#         "id": 123,
#         "name": "John Doe",
#         "email": "john@example.com",
#         "created_at": datetime(2024, 1, 15, 10, 30, 45, 123456)
#     }

#     prev_hash = "0" * 64
#     tx_id = "test-uuid-123"
#     record_id = "123"
#     op_type = "INSERT"
#     created_at = test_data["created_at"]

#     results = {}

#     # Test row hash
#     row_hash_1 = compute_row_hash(test_data, prev_hash)
#     row_hash_2 = compute_row_hash(test_data, prev_hash)
#     results["row_hash_consistency"] = row_hash_1 == row_hash_2

#     # Test chain hash
#     chain_hash_1 = compute_chain_hash(prev_hash, tx_id, record_id, op_type, None, test_data, created_at)
#     chain_hash_2 = compute_chain_hash(prev_hash, tx_id, record_id, op_type, None, test_data, created_at)
#     results["chain_hash_consistency"] = chain_hash_1 == chain_hash_2

#     # Test record hash
#     record_hash_1 = compute_record_hash(record_id, test_data)
#     record_hash_2 = compute_record_hash(record_id, test_data)
#     results["record_hash_consistency"] = record_hash_1 == record_hash_2

#     # Test Merkle hash
#     left_hash = "a" * 64
#     right_hash = "b" * 64
#     merkle_hash_1 = compute_merkle_hash(left_hash, right_hash)
#     merkle_hash_2 = compute_merkle_hash(left_hash, right_hash)
#     results["merkle_hash_consistency"] = merkle_hash_1 == merkle_hash_2

#     # Test datetime canonicalization
#     dt1 = canonicalize_datetime(created_at)
#     dt2 = canonicalize_datetime(created_at)
#     results["datetime_canonicalization"] = dt1 == dt2

#     # Test JSON canonicalization
#     json1 = canonicalize_json(test_data)
#     json2 = canonicalize_json(test_data)
#     results["json_canonicalization"] = json1 == json2

#     return results


# # ============================================================
# # === Entry Point ============================================
# # ============================================================

# if __name__ == "__main__":
#     """Run consistency tests when module is executed directly."""
#     print("🔍 Testing Maria Ledger Hash Consistency...")
#     results = verify_hash_consistency()
#     all_passed = True

#     for test_name, passed in results.items():
#         status = "✅" if passed else "❌"
#         print(f"{status} {test_name}: {'PASSED' if passed else 'FAILED'}")
#         if not passed:
#             all_passed = False

#     if all_passed:
#         print("\n🎉 All hash consistency tests passed!")
#     else:
#         print("\n⚠️ Some hash consistency tests failed!")

#     exit(0 if all_passed else 1)
