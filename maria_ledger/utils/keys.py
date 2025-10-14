import base64
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives import serialization

def load_private_key(path: str):
    pem = Path(path).read_bytes()
    return serialization.load_pem_private_key(pem, password=None)

def load_public_key(path: str):
    pem = Path(path).read_bytes()
    return serialization.load_pem_public_key(pem)

def public_key_fingerprint_pem_bytes(pem_bytes: bytes) -> str:
    # SHA256 hex digest of the PEM bytes (stable fingerprint)
    return hashlib.sha256(pem_bytes).hexdigest()

def public_key_fingerprint_from_file(path: str) -> str:
    pem = Path(path).read_bytes()
    return public_key_fingerprint_pem_bytes(pem)
