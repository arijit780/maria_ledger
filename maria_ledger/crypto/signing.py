import base64
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from maria_ledger.utils.keys import load_private_key, load_public_key, public_key_fingerprint_from_file

def sign_message(private_key_path: str, message: str) -> (str, str):
    """
    Sign the message (UTF-8 string). Returns (signature_b64, pubkey_fingerprint_hex).
    """
    priv = load_private_key(private_key_path)
    sig = priv.sign(
        message.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    sig_b64 = base64.b64encode(sig).decode("ascii")
    # compute fingerprint of public key file (caller should pass config path)
    # caller may compute fingerprint separately; optionally returned by this function
    return sig_b64

def verify_signature(public_key_path: str, message: str, signature_b64: str) -> bool:
    pub = load_public_key(public_key_path)
    sig = base64.b64decode(signature_b64)
    try:
        pub.verify(
            sig,
            message.encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return True
    except Exception:
        return False
