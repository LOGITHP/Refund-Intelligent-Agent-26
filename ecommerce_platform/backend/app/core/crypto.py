"""Application-level AES-256-GCM encryption and secret redaction utilities."""

import base64
import binascii
from decimal import Decimal
import hashlib
import os
import re
from typing import Any, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_SIZE_BYTES = 12  # 96-bit NIST-recommended nonce for AES-GCM
MIN_TAG_SIZE_BYTES = 16  # 128-bit authentication tag appended by AESGCM

_SENSITIVE_KEYS = {
    "authorization",
    "access_token",
    "refresh_token",
    "client_secret",
    "paypal_client_secret",
    "secret",
    "secret_key",
    "app_data_encryption_key",
    "password",
    "hashed_password",
    "paypal-transmission-sig",
    "transmission_sig",
    "api_key",
    "x-api-key",
    "cookie",
    "set-cookie",
}

_BEARER_OR_BASIC_RE = re.compile(
    r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9\-._~+/]+=*"
)


def _derive_aes256_key(raw_key: Optional[str] = None) -> bytes:
    """Resolves a 256-bit (32-byte) AES key from hex, base64, raw 32-byte, or >=16-char secret."""
    key_str = (raw_key if raw_key is not None else settings.APP_DATA_ENCRYPTION_KEY).strip()
    if not key_str:
        raise ValueError("APP_DATA_ENCRYPTION_KEY is not configured")

    # 1. 64-char hex string -> exact 32 bytes
    if len(key_str) == 64:
        try:
            decoded_hex = bytes.fromhex(key_str)
            if len(decoded_hex) == 32:
                return decoded_hex
        except ValueError:
            pass

    # 2. Base64 / URL-safe Base64 encoded 32-byte key
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            padded = key_str + ("=" * ((4 - len(key_str) % 4) % 4))
            decoded = decoder(padded.encode("ascii"))
            if len(decoded) == 32:
                return decoded
        except (binascii.Error, UnicodeEncodeError, ValueError):
            continue

    # 3. Direct 32-byte UTF-8 key
    raw_bytes = key_str.encode("utf-8")
    if len(raw_bytes) == 32:
        return raw_bytes

    # 4. Passphrase >= 16 chars -> SHA-256 digest to 32 bytes
    if len(key_str) >= 16:
        return hashlib.sha256(raw_bytes).digest()

    raise ValueError(
        "APP_DATA_ENCRYPTION_KEY must be a 32-byte base64/hex key or at least 16 characters"
    )


def encrypt_secret(
    plaintext: str,
    *,
    key: Optional[str] = None,
    associated_data: Optional[bytes] = None,
) -> str:
    """Encrypts plaintext using AES-256-GCM with a unique 96-bit random nonce and URL-safe base64."""
    if plaintext is None:
        raise ValueError("Plaintext must not be None")
    key_bytes = _derive_aes256_key(key)
    nonce = os.urandom(NONCE_SIZE_BYTES)
    aesgcm = AESGCM(key_bytes)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data)
    return base64.urlsafe_b64encode(nonce + ciphertext_with_tag).decode("ascii")


def decrypt_secret(
    ciphertext_b64: str,
    *,
    key: Optional[str] = None,
    associated_data: Optional[bytes] = None,
) -> str:
    """Decrypts an AES-256-GCM URL-safe base64 token (96-bit nonce + ciphertext + 128-bit tag)."""
    if not ciphertext_b64:
        raise ValueError("Ciphertext must not be empty")
    key_bytes = _derive_aes256_key(key)
    try:
        padded = ciphertext_b64 + ("=" * ((4 - len(ciphertext_b64) % 4) % 4))
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise ValueError("Invalid base64 ciphertext payload") from exc

    if len(raw) < NONCE_SIZE_BYTES + MIN_TAG_SIZE_BYTES:
        raise ValueError("Ciphertext payload is too short to contain nonce and GCM tag")

    nonce = raw[:NONCE_SIZE_BYTES]
    ciphertext_with_tag = raw[NONCE_SIZE_BYTES:]
    aesgcm = AESGCM(key_bytes)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, associated_data)
    return plaintext_bytes.decode("utf-8")


def redact_sensitive_data(value: Any) -> Any:
    """Recursively scrubs secret credentials/tokens and normalizes Decimals for safe audit logging."""
    if isinstance(value, dict):
        sanitized = {}
        for k, v in value.items():
            key_lower = str(k).strip().lower()
            if (
                key_lower in _SENSITIVE_KEYS
                or key_lower.endswith("_secret")
                or key_lower.endswith("_password")
            ):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = redact_sensitive_data(v)
        return sanitized
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return _BEARER_OR_BASIC_RE.sub(r"\1 [REDACTED]", value)
    return value
