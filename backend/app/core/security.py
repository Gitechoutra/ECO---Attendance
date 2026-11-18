import hashlib
import secrets
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.db.base import utcnow

_hasher = PasswordHasher()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not any(c.isupper() for c in password) or not any(c.islower() for c in password):
        return "Password must contain upper and lower case letters."
    if not any(c.isdigit() for c in password):
        return "Password must contain a number."
    return None


def create_access_token(user_id: int, role: str, token_version: int) -> str:
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,
        "tv": token_version,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _fernet(key: str) -> Fernet:
    if not key:
        raise RuntimeError("Encryption key is not configured")
    return Fernet(key.encode())


def encrypt_bytes(data: bytes, biometric: bool = False) -> bytes:
    key = settings.BIOMETRIC_ENCRYPTION_KEY if biometric else settings.DATA_ENCRYPTION_KEY
    return _fernet(key).encrypt(data)


def decrypt_bytes(token: bytes, biometric: bool = False) -> bytes:
    key = settings.BIOMETRIC_ENCRYPTION_KEY if biometric else settings.DATA_ENCRYPTION_KEY
    try:
        return _fernet(key).decrypt(token)
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt data — encryption key mismatch") from exc


def encrypt_str(value: str | None) -> str | None:
    if value in (None, ""):
        return value
    return encrypt_bytes(value.encode()).decode()


def decrypt_str(value: str | None) -> str | None:
    if value in (None, ""):
        return value
    return decrypt_bytes(value.encode()).decode()
