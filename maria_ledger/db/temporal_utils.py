# temporal_utils.py - Note: Parts of this file are for the old architecture.
from datetime import datetime, timezone
from collections import defaultdict, Counter
from typing import List, Dict, Any, Tuple
import json
import hashlib
from maria_ledger.db.connection import get_connection

def iso(ts):
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).isoformat()
    return str(ts)

# --- Core walker (Old Architecture - for system-versioned tables) ----------------
def walk_temporal_chain(conn, table_name: str, batch_size: int = 10000):
    """
    Walk rows ordered by valid_from.
    Yields rows as dicts with keys: id, row_hash, prev_hash, valid_from, ... 
    """
    with conn.cursor(dictionary=True) as cur:
        cur.execute(f"""
            SELECT id, row_hash, prev_hash, valid_from
            FROM `{table_name}`
            ORDER BY valid_from ASC, id ASC
        """)
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            for r in rows:
                yield r

# --- Anomaly detections (Old Architecture) -------------------------------------
def analyze_temporal_chain(table_name: str) -> Dict[str, Any]:
    """
    Returns a report with detected anomalies and a risk_score [0..100].
    """
    conn = get_connection()
    try:
        anomalies = []
        prev_row = None
        seen_prev_hashes = Counter()
        seen_row_hashes = set()
        last_valid_from_by_id = {}  # for per-id monotonic checks
        index = 0

        # For fork detection: map prev_hash -> list of row_hash that point to it
        prev_to_children = defaultdict(list)

        for row in walk_temporal_chain(conn, table_name):
            index += 1
            id_ = row.get("id")
            rh = row.get("row_hash")
            ph = row.get("prev_hash")
            vf = row.get("valid_from")

            # basic presence checks
            if not rh:
                anomalies.append({"type": "missing_row_hash", "index": index, "id": id_, "detail": "row_hash missing"})
            if ph is None:
                anomalies.append({"type": "missing_prev_hash", "index": index, "id": id_, "detail": "prev_hash is NULL"})

            # check prev pointer chain continuity
            if prev_row is not None:
                if ph != prev_row.get("row_hash"):
                    anomalies.append({
                        "type": "prev_hash_mismatch",
                        "index": index,
                        "id": id_,
                        "detail": f"prev_hash ({ph}) != previous row_hash ({prev_row.get('row_hash')})",
                        "prev_index": index - 1
                    })

            # timestamp monotonicity per global order
            if prev_row is not None:
                prev_vf = prev_row.get("valid_from")
                if vf and prev_vf and vf < prev_vf:
                    anomalies.append({
                        "type": "timestamp_non_monotonic",
                        "index": index,
                        "id": id_,
                        "detail": f"valid_from {iso(vf)} < previous valid_from {iso(prev_vf)}"
                    })

            # per-entity monotonic check (if multiple versions for same business id)
            if id_ is not None:
                last_v = last_valid_from_by_id.get(id_)
                if last_v and vf and vf <= last_v:
                    anomalies.append({
                        "type": "per_id_time_rewind",
                        "index": index,
                        "id": id_,
                        "detail": f"valid_from {iso(vf)} <= last valid_from {iso(last_v)} for id {id_}"
                    })
                last_valid_from_by_id[id_] = vf

            # duplicate row hash detection (replays)
            if rh in seen_row_hashes:
                anomalies.append({
                    "type": "duplicate_row_hash",
                    "index": index,
                    "id": id_,
                    "detail": f"row_hash {rh} already seen (possible replay)"
                })
            else:
                seen_row_hashes.add(rh)

            # fork detection mapping
            prev_to_children[ph].append(rh)
            seen_prev_hashes[ph] += 1

            prev_row = row

        # evaluate forks (prev_hash pointed by >1 child)
        forks = []
        for prev_h, children in prev_to_children.items():
            if prev_h and len(children) > 1:
                forks.append({"prev_hash": prev_h, "children_count": len(children), "children": children})

        if forks:
            anomalies.append({"type": "forks_detected", "detail": forks})

        # gaps: quick heuristic - any prev_hash where referenced row_hash is absent in set
        missing_links = []
        for prev_h in seen_prev_hashes:
            if prev_h and prev_h not in seen_row_hashes:
                missing_links.append(prev_h)
        if missing_links:
            anomalies.append({"type": "missing_link_targets", "count": len(missing_links), "examples": missing_links[:5]})

        # risk scoring: simple heuristic
        score = 0
        weight_map = {
            "missing_row_hash": 30,
            "missing_prev_hash": 15,
            "prev_hash_mismatch": 35,
            "timestamp_non_monotonic": 25,
            "per_id_time_rewind": 20,
            "duplicate_row_hash": 30,
            "forks_detected": 40,
            "missing_link_targets": 30
        }
        for a in anomalies:
            t = a.get("type")
            score += weight_map.get(t, 10)
        # normalize
        risk_score = min(100, score)

        report = {
            "table": table_name,
            "rows_scanned": index,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "risk_score": risk_score,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        return report
    finally:
        conn.close()

# --- Anomaly detections (New Universal Ledger Architecture) -------------------
def analyze_universal_ledger_chain(table_name: str) -> Dict[str, Any]:
    """
    Analyzes the universal `ledger` table for a specific logical table.
    Returns a report with detected anomalies and a risk_score [0..100].
    """
    conn = get_connection()
    try:
        anomalies = []
        index = 0
        prev_tx_order = 0
        prev_created_at = None
        prev_row_hash = None
        seen_tx_ids = set()

        sql = "SELECT tx_id, tx_order, op_type, record_id, old_payload, new_payload, created_at FROM ledger WHERE table_name = %s ORDER BY tx_order ASC"
        
        with conn.cursor(dictionary=True, buffered=False) as cur:
            cur.execute(sql, (table_name,))
            
            rows = list(cur)
            for i, row in enumerate(rows):
                index += 1
                tx_id = row['tx_id']
                tx_order = row['tx_order']
                created_at = row['created_at']

                # 1. Check for gaps in the tx_order sequence
                if prev_tx_order > 0 and tx_order != prev_tx_order + 1:
                    anomalies.append({
                        "type": "tx_order_gap",
                        "index": index,
                        "detail": f"Gap detected in tx_order. Jumped from {prev_tx_order} to {tx_order}."
                    })

                # 2. Check for timestamp non-monotonicity
                if prev_created_at is not None and created_at < prev_created_at:
                    anomalies.append({
                        "type": "timestamp_non_monotonic",
                        "index": index,
                        "detail": f"Timestamp rewind detected. {iso(created_at)} is before previous {iso(prev_created_at)}."
                    })

                # 3. Check for duplicate tx_id
                if tx_id in seen_tx_ids:
                    anomalies.append({
                        "type": "duplicate_tx_id",
                        "index": index,
                        "detail": f"Duplicate tx_id {tx_id} found."
                    })
                seen_tx_ids.add(tx_id)

                # 4. Hash chain verification
                current_row_hash = hashlib.sha256(
                    (
                        str(row.get('old_payload', 'n/a')) +
                        str(row.get('new_payload', 'n/a')) +
                        str(row.get('op_type', 'n/a')) +
                        str(row.get('record_id', 'n/a')) +
                        str(iso(row.get('created_at', 'n/a')))
                    ).encode('utf-8')
                ).hexdigest()

                if i > 0 and prev_row_hash != tx_id:
                     anomalies.append({
                        "type": "hash_chain_mismatch",
                        "index": index,
                        "detail": f"Hash chain broken at tx_order {tx_order}. Expected {prev_row_hash} but got {tx_id}."
                    })

                prev_tx_order = tx_order
                prev_created_at = created_at
                prev_row_hash = current_row_hash

        if index == 0:
            return { "table": table_name, "rows_scanned": 0, "anomaly_count": 0, "anomalies": [], "risk_score": 0 }

        # Risk scoring
        score = 0
        weight_map = {
            "tx_order_gap": 50,
            "timestamp_non_monotonic": 30,
            "duplicate_tx_id": 40,
            "hash_chain_mismatch": 60,
        }
        for a in anomalies:
            score += weight_map.get(a.get("type"), 10)
        
        risk_score = min(100, score)

        report = {
            "table": table_name,
            "rows_scanned": index,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "risk_score": risk_score,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        return report

    finally:
        conn.close()
