import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from backend.config import settings
from backend.models.user import UserRole


def generate_secure_password(length: int = 12) -> str:
    """Generate an alphanumeric password with symbols that is easy to read and secure."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^&*" for c in password)):
            return password


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt. Returns a UTF-8 string for DB storage."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: uuid.UUID, email: str, role: UserRole) -> str:
    expire = datetime.now(timezone.utc).timestamp() + settings.jwt_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role.value,
        "exp": int(expire),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """Returns the decoded payload or None if the token is invalid/expired."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None
