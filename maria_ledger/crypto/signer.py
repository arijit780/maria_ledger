# maria_ledger/crypto/signer.py
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
from base64 import b64encode, b64decode
from maria_ledger.utils.logger import get_logger

logger = get_logger("signer")

def generate_keypair(private_key_path="private.pem", public_key_path="public.pem"):
    """Generate a new RSA keypair and save to disk."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    public_bytes = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(private_key_path, "wb") as f:
        f.write(private_bytes)
    with open(public_key_path, "wb") as f:
        f.write(public_bytes)
    logger.info(f"Generated keypair: {private_key_path}, {public_key_path}")
    return private_key_path, public_key_path


def sign_merkle_root(private_key_path: str, merkle_root: str) -> str:
    """Sign a Merkle root using RSA private key and return base64 signature."""
    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
    signature = private_key.sign(
        merkle_root.encode(),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    encoded = b64encode(signature).decode()
    logger.info("Merkle root signed successfully.")
    return encoded


def verify_merkle_root_signature(public_key_path: str, merkle_root: str, signature_b64: str) -> bool:
    """Verify signature of a Merkle root using RSA public key."""
    with open(public_key_path, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read(), backend=default_backend())
    try:
        public_key.verify(
            b64decode(signature_b64),
            merkle_root.encode(),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        logger.warning(f"Verification failed: {e}")
        return False
