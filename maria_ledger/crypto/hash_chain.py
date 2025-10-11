import hashlib
import json
from datetime import datetime, date

def compute_row_hash(row_dict, prev_hash: str) -> str:
    """
    Compute SHA256 hash of row contents + prev_hash.
    Convert datetime objects to ISO format strings for deterministic hashing.
    """
    canonical_dict = {}
    for k, v in row_dict.items():
        if isinstance(v, (datetime, date)):
            canonical_dict[k] = v.isoformat()
        else:
            canonical_dict[k] = v

    canonical = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
    data = canonical + prev_hash
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
