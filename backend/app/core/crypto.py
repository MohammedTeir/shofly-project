from cryptography.fernet import Fernet, MultiFernet
from app.core.config import get_settings
from app.core.errors import AppError


def _f() -> MultiFernet:
    """ENCRYPTION_KEY may hold several comma-separated keys: the first encrypts, all can decrypt (key rotation)."""
    keys = [k.strip() for k in (get_settings().encryption_key or "").split(",") if k.strip()]
    if not keys:
        raise AppError(503, "ENCRYPTION_NOT_CONFIGURED", "Server encryption key is not configured.")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(s: str) -> str: return _f().encrypt(s.encode()).decode()
def decrypt(s: str) -> str: return _f().decrypt(s.encode()).decode()
