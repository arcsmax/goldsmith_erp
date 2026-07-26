import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from goldsmith_erp.core.config import settings

# Passwort-Hash-Kontext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT-Konfiguration
ALGORITHM = "HS256"

# Grace window: how many seconds after expiry a token may still be refreshed.
# This allows a token that expired moments ago to be exchanged for a fresh one
# without forcing the user to re-authenticate.
REFRESH_GRACE_SECONDS = 5 * 60  # 5 minutes


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifiziert ein Klartext-Passwort gegen einen Hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generiert einen Hash für ein Passwort."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generiert ein JWT-Token mit optionaler Ablaufzeit.

    Every token carries a unique ``jti`` (uuid4) so it can be individually
    blocklisted on logout, and an ``iat`` (issued-at) timestamp so a per-user
    "invalid-before" mark can revoke every outstanding token on password change
    without enumerating each jti (see core/token_revocation.py, finding 2.1).
    """
    to_encode = data.copy()

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": expire,
            # Sub-second iat (RFC 7519 NumericDate permits fractional seconds).
            # The per-user invalid-before mark compares iat against a wall-clock
            # cutoff; second-resolution iat could not distinguish a token issued
            # just before a password change from the fresh one issued just after
            # it in the same second, so we keep full precision here.
            "iat": now.timestamp(),
            "jti": uuid.uuid4().hex,
        }
    )
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token_allowing_grace_window(token: str) -> dict:
    """Decode a JWT and allow recently-expired tokens within REFRESH_GRACE_SECONDS.

    This is used exclusively by the /auth/refresh endpoint so that a client whose
    token expired at most REFRESH_GRACE_SECONDS ago can still obtain a new token
    without being forced to re-authenticate with credentials.

    Raises:
        JWTError: if the token is structurally invalid, has a bad signature,
                  or has been expired for longer than the grace window.
    """
    # Decode without expiry enforcement so we can apply the grace window ourselves.
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"verify_exp": False},
    )

    exp = payload.get("exp")
    if exp is None:
        raise JWTError("Token has no expiry claim (exp)")

    now_utc = datetime.now(timezone.utc).timestamp()
    if now_utc > exp + REFRESH_GRACE_SECONDS:
        raise JWTError(
            f"Token expired more than {REFRESH_GRACE_SECONDS // 60} minutes ago "
            "and cannot be refreshed"
        )

    return payload
