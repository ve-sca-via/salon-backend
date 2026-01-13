"""
Encryption helpers for sensitive configuration values.

Provides a lightweight wrapper around Fernet symmetric encryption.
If `DB_ENCRYPTION_KEY` is not provided, a No-op encryption service is returned
to avoid breaking local development and tests. In production you MUST set
`DB_ENCRYPTION_KEY` to a base64-encoded 32-byte key (Fernet key).
"""
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet
except Exception as e:
    Fernet = None
    logger.debug("cryptography.Fernet not available: %s", e)


class EncryptionService:
    def __init__(self, key: bytes):
        if Fernet is None:
            raise RuntimeError("cryptography is required for EncryptionService")
        self._fernet = Fernet(key)

    def encrypt_value(self, plain_text: str) -> str:
        if plain_text is None:
            return plain_text
        token = self._fernet.encrypt(plain_text.encode())
        encrypted = token.decode()
        logger.debug(f"Encrypted value (first 20 chars): {encrypted[:20]}...")
        return encrypted

    def decrypt_value(self, encrypted_text: str) -> str:
        if encrypted_text is None:
            return encrypted_text
        plain = self._fernet.decrypt(encrypted_text.encode())
        return plain.decode()
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key for encryption"""
        if Fernet is None:
            raise RuntimeError("cryptography is required to generate keys")
        return Fernet.generate_key().decode()


class NoopEncryptionService:
    """Fallback service used when no encryption key is configured.

    This avoids breaking local development and tests. In production you must
    provide `DB_ENCRYPTION_KEY` and remove the No-op behaviour.
    """
    def encrypt_value(self, plain_text: str) -> str:
        logger.debug("NoopEncryptionService: returning plain text (no encryption)")
        return plain_text

    def decrypt_value(self, encrypted_text: str) -> str:
        return encrypted_text
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key for encryption"""
        if Fernet is None:
            raise RuntimeError("cryptography is required to generate keys")
        return Fernet.generate_key().decode()


# Singleton holder
_SERVICE: Optional[object] = None


def get_encryption_service():
    """Return a singleton encryption service.

    Priority:
    - If `DB_ENCRYPTION_KEY` env var exists (base64 Fernet key), return real
      `EncryptionService`.
    - Otherwise return `NoopEncryptionService` and log a warning.
    """
    global _SERVICE
    if _SERVICE is not None:
        return _SERVICE

    key = os.getenv("DB_ENCRYPTION_KEY")
    if key:
        try:
            # Accept either raw Fernet key or base64-encoded
            if isinstance(key, str):
                key_bytes = key.encode()
            else:
                key_bytes = key
            _SERVICE = EncryptionService(key_bytes)
            logger.info("EncryptionService initialized using DB_ENCRYPTION_KEY")
            return _SERVICE
        except Exception as e:
            logger.error("Failed to initialize EncryptionService: %s", e)

    logger.warning("DB_ENCRYPTION_KEY not set - using NoopEncryptionService (development/test only)")
    _SERVICE = NoopEncryptionService()
    return _SERVICE
