import math
from typing import Optional
from .hash_utils import compute_merkle_hash

class MerkleTree:
    def __init__(self, leaves: list[str]):
        self.leaves = leaves
        self.levels = []
        self.root: Optional[str] = None
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
                combined = compute_merkle_hash(left, right)
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
                computed = compute_merkle_hash(computed, sibling_hash)
            else:
                computed = compute_merkle_hash(sibling_hash, computed)
            idx = idx // 2
        return computed == root


@classmethod
def create_from_hashes(cls, hashes: list[str]) -> 'MerkleTree':
    """
    Factory method to create a MerkleTree from a list of hashes.
    """
    return cls(hashes)