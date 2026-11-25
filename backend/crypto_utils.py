import os
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

def get_master_aes_key() -> bytes:
    """Retrieve or generate 32-byte AES key from app config/environment."""
    key_hex = os.getenv("AES_SECRET_KEY")
    if not key_hex and current_app:
        key_hex = current_app.config.get("AES_SECRET_KEY")
    
    if key_hex:
        try:
            key_bytes = bytes.fromhex(key_hex)
            if len(key_bytes) == 32:
                return key_bytes
        except ValueError:
            pass
            
    # Fallback to deterministic 32-byte hash of secret or generate
    fallback = os.getenv("SECRET_KEY", "medichain-super-secret-key-2026")
    return hashlib.sha256(fallback.encode("utf-8")).digest()

def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of bytes and return 64-character lowercase hex string."""
    hasher = hashlib.sha256()
    hasher.update(data)
    return hasher.hexdigest()

def encrypt_document(data: bytes, key_bytes: bytes = None) -> tuple[bytes, str, str]:
    """
    Encrypt document data using AES-256-GCM.
    Returns (encrypted_payload, iv_hex, tag_hex).
    - 12-byte cryptographically secure random nonce/IV.
    - 16-byte GCM authentication tag.
    """
    if key_bytes is None:
        key_bytes = get_master_aes_key()

    aesgcm = AESGCM(key_bytes)
    nonce = os.urandom(12) # Standard 96-bit nonce for GCM
    
    # AESGCM encrypt appends 16-byte tag to the ciphertext
    ct_with_tag = aesgcm.encrypt(nonce, data, None)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    iv_hex = nonce.hex()
    tag_hex = tag.hex()
    return ct_with_tag, iv_hex, tag_hex

def decrypt_document(encrypted_data: bytes, iv_hex: str, tag_hex: str, key_bytes: bytes = None) -> bytes:
    """
    Decrypt document data using AES-256-GCM and verify authenticity tag.
    Raises ValueError if key, IV, or tag is invalid or data was tampered with.
    """
    if key_bytes is None:
        key_bytes = get_master_aes_key()

    nonce = bytes.fromhex(iv_hex)
    aesgcm = AESGCM(key_bytes)

    # In case encrypted_data doesn't include tag, recombine
    if len(encrypted_data) > 0:
        # Check if tag is already at the end
        expected_tag = bytes.fromhex(tag_hex)
        if encrypted_data[-16:] == expected_tag:
            full_ct = encrypted_data
        else:
            full_ct = encrypted_data + expected_tag
    else:
        full_ct = bytes.fromhex(tag_hex)

    decrypted = aesgcm.decrypt(nonce, full_ct, None)
    return decrypted

def verify_document_integrity(decrypted_bytes: bytes, original_blockchain_hash: str) -> tuple[bool, str]:
    """
    Recalculates SHA-256 hash of decrypted document and compares with blockchain registered hash.
    Returns (is_valid, calculated_hash).
    """
    calculated_hash = compute_sha256(decrypted_bytes)
    is_valid = (calculated_hash.lower() == original_blockchain_hash.lower())
    return is_valid, calculated_hash
