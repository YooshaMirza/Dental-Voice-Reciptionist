"""
Password hashing + JWT issuance/verification.

Password hashing uses Django's own pbkdf2_sha256 scheme (via passlib) so any
existing api_customuser password hashes created by the old Django app keep
working without a data migration.
"""
import datetime
import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["django_pbkdf2_sha256"], deprecated="auto")

JWT_ALGORITHM = "HS256"


def hash_password(raw_password: str) -> str:
    return pwd_context.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(raw_password, hashed_password)
    except Exception:
        return False


def _create_token(user_id: str, token_type: str, lifetime: datetime.timedelta) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": str(user_id),
        "token_type": token_type,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(
        user_id, "access", datetime.timedelta(minutes=settings.ACCESS_TOKEN_LIFETIME_MINUTES)
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        user_id, "refresh", datetime.timedelta(days=settings.REFRESH_TOKEN_LIFETIME_DAYS)
    )


def decode_token(token: str) -> dict:
    """Raises jwt.InvalidTokenError (or a subclass) if the token is invalid/expired."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
