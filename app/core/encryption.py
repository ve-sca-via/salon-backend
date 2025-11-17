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
        return token.decode()

    def decrypt_value(self, encrypted_text: str) -> str:
        if encrypted_text is None:
            return encrypted_text
        plain = self._fernet.decrypt(encrypted_text.encode())
        return plain.decode()


class NoopEncryptionService:
    """Fallback service used when no encryption key is configured.

    This avoids breaking local development and tests. In production you must
    provide `DB_ENCRYPTION_KEY` and remove the No-op behaviour.
    """
    def encrypt_value(self, plain_text: str) -> str:
        return plain_text

    def decrypt_value(self, encrypted_text: str) -> str:
        return encrypted_text


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
"""
Encryption service for sensitive data (payment credentials, etc.)
Uses Fernet symmetric encryption for PCI DSS compliance
"""
from cryptography.fernet import Fernet
import os
import base64
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class EncryptionService:
    """Service for encrypting/decrypting sensitive configuration values"""

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption service

        Args:
            encryption_key: Base64-encoded Fernet key. If None, uses env var.
        """
        if encryption_key:
            self.key = encryption_key
        else:
            self.key = os.getenv("DB_ENCRYPTION_KEY")

        if not self.key:
            raise ValueError("DB_ENCRYPTION_KEY environment variable must be set")

        try:
            self.cipher = Fernet(self.key.encode())
        except Exception as e:
            raise ValueError(f"Invalid encryption key: {e}")

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key for encryption"""
        return Fernet.generate_key().decode()

    def encrypt_value(self, plain_text: str) -> str:
        """
        Encrypt a plain text value

        Args:
            plain_text: Value to encrypt

        Returns:
            Base64-encoded encrypted value
        """
        if not plain_text:
            return plain_text

        try:
            encrypted = self.cipher.encrypt(plain_text.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError(f"Failed to encrypt value: {e}")

    def decrypt_value(self, encrypted_text: str) -> str:
        """
        Decrypt an encrypted value

        Args:
            encrypted_text: Base64-encoded encrypted value

        Returns:
            Decrypted plain text
        """
        if not encrypted_text:
            return encrypted_text

        try:
            decrypted = self.cipher.decrypt(encrypted_text.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Failed to decrypt value: {e}")

    def is_encrypted(self, value: str) -> bool:
        """
        Check if a value appears to be encrypted (basic heuristic)

        Args:
            value: Value to check

        Returns:
            True if value appears encrypted
        """
        if not value:
            return False

        try:
            # Try to decode as base64 and check if it looks like Fernet data
            decoded = base64.urlsafe_b64decode(value)
            return len(decoded) >= 73  # Fernet tokens are at least 73 bytes
        except:
            return False


# Global encryption service instance
_encryption_service: Optional[EncryptionService] = None

def get_encryption_service() -> EncryptionService:
    """Get or create global encryption service instance"""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service