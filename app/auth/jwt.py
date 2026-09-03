from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings

# Algorithm is fixed here — not exposed as a configurable env variable.
# Changing the signing algorithm requires a code change, not just a config tweak,
# because it affects token compatibility across all issued tokens.
_ALGORITHM = "HS256"

settings = get_settings()


class TokenError(Exception):
    pass


class TokenExpiredError(TokenError):
    pass


class TokenInvalidError(TokenError):
    pass


def create_token(
    user_id: str, username: str, role: str, email: str = "", expiry_minutes: int | None = None
) -> str:
    minutes = expiry_minutes if expiry_minutes is not None else settings.jwt_expiry_minutes
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "username": username,
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredError("Token has expired.") from e
    except jwt.InvalidTokenError as e:
        raise TokenInvalidError(f"Invalid token: {e}") from e


def extract_user_id(token: str) -> str:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise TokenInvalidError("Token missing 'sub' claim.")
    return user_id
