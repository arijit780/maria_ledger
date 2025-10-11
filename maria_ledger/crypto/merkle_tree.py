import hashlib
import math
from maria_ledger.db.connection import get_connection

def sha256(data: str) -> str:
    return hashlib.sha256(data.encode('utf-8')).hexdigest()

class MerkleTree:
    def __init__(self, leaves: list[str]):
        self.leaves = leaves
        self.levels = []
        if leaves:
            self.build_tree()

    def build_tree(self):
        current_level = self.leaves.copy()
        self.levels.append(current_level)
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i+1] if i+1 < len(current_level) else left
                combined = sha256(left + right)
                next_level.append(combined)
            current_level = next_level
            self.levels.append(current_level)
        self.root = self.levels[-1][0]

    def get_root(self) -> str:
        return self.root

    def get_proof(self, index: int) -> list[str]:
        """
        Returns a Merkle proof for a given leaf index.
        Proof is a list of sibling hashes needed to reconstruct root.
        """
        proof = []
        idx = index
        for level in self.levels[:-1]:
            sibling_idx = idx + 1 if idx % 2 == 0 else idx - 1
            if sibling_idx < len(level):
                proof.append(level[sibling_idx])
            idx = idx // 2
        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: list[str], root: str, index: int) -> bool:
        computed = leaf_hash
        idx = index
        for sibling_hash in proof:
            if idx % 2 == 0:
                computed = sha256(computed + sibling_hash)
            else:
                computed = sha256(sibling_hash + computed)
            idx = idx // 2
        return computed == root


def verify_table_with_merkle_root(table_name: str, root_hash: str) -> bool:
    """
    Fetch row_hashes from table, rebuild Merkle tree, and compare with provided root_hash.
    Returns True if root matches.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT row_hash FROM {table_name} ORDER BY valid_from ASC")
    hashes = [row['row_hash'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    if not hashes:
        return False  # empty table

    tree = MerkleTree(hashes)
    return tree.get_root() == root_hash