import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Define the output directory for the keys, relative to the project root
KEYS_DIR = "keys"

# Create the directory if it doesn't exist
os.makedirs(KEYS_DIR, exist_ok=True)

# Define file paths
private_key_path = os.path.join(KEYS_DIR, "private_key.pem")
public_key_path = os.path.join(KEYS_DIR, "public_key.pem")

# Generate a 4096-bit RSA private key
private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

# Serialize and save the private key
pem_priv = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
with open(private_key_path, "wb") as f:
    f.write(pem_priv)

# Derive, serialize, and save the public key
pub = private_key.public_key()
pem_pub = pub.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)
with open(public_key_path, "wb") as f:
    f.write(pem_pub)

print(f"Wrote private_key.pem and public_key.pem to '{KEYS_DIR}/' directory.")
