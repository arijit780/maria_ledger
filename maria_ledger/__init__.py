"""Maria Ledger - Tamper-evident database ledger system."""

__version__ = "0.1.0"

from typing import List, Optional, Dict, Any
from maria_ledger.crypto.merkle_tree import MerkleTree
from maria_ledger.db.connection import get_connection
from maria_ledger.utils.bootstrap_utils import bootstrap_table_core

__all__ = ["MerkleTree", "get_connection", "make_tamper_evident", "__version__"]


def make_tamper_evident(
    table_name: str,
    fields: Optional[List[str]] = None,
    primary_key: Optional[str] = None,
    snapshot_existing: bool = True,
    create_checkpoint: bool = True,
) -> Dict[str, Any]:
    """
    Make any table tamper-evident by setting up ledger tracking.

    This function automatically:
      - Detects table schema (or uses provided primary_key)
      - Snapshots existing data (if snapshot_existing=True)
      - Creates database triggers for INSERT/UPDATE/DELETE
      - Creates initial Merkle root checkpoint (if create_checkpoint=True)

    Args:
        table_name: Name of the table to make tamper-evident.
        fields: Optional list of column names to track. If None, tracks all columns.
        primary_key: Optional primary key column name. If None, auto-detected from schema.
        snapshot_existing: Whether to snapshot existing table data into ledger (default: True)
        create_checkpoint: Whether to create initial Merkle root checkpoint (default: True)

    Returns:
        Dict with:
            - success (bool): Whether operation succeeded
            - merkle_root (str|None): Computed Merkle root if checkpoint was created
            - records_snapshotted (int): Number of records snapshotted
            - primary_key (str): Primary key column used
            - columns_tracked (list): List of columns being tracked
            - error (str|None): Error message if operation failed

    Raises:
        ValueError: If table doesn't exist, has no primary key, or invalid parameters.
        RuntimeError: If bootstrap operation fails.

    Example:
        >>> result = make_tamper_evident('my_table')
        >>> print(result['success'])
        True

        # Track only specific fields
        >>> result = make_tamper_evident('customers', fields=['name', 'email'])

        # Custom primary key
        >>> result = make_tamper_evident('products', primary_key='product_id')
    """
    result = bootstrap_table_core(
        table_name=table_name,
        fields=fields,
        primary_key=primary_key,
        snapshot_existing=snapshot_existing,
        create_checkpoint=create_checkpoint,
    )

    if not result["success"]:
        error_msg = result.get("error", "Unknown error")
        raise RuntimeError(f"Failed to make table '{table_name}' tamper-evident: {error_msg}")

    return result
