from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.email_role import get_role_for_email
from app.auth.jwt import TokenExpiredError, TokenInvalidError, decode_token
from app.database import get_db
from app.models.role import Role
from app.models.user import User

_bearer = HTTPBearer()


def _synthetic_user(user_id: str, username: str, email: str, role_name: str) -> User:
    """Build an in-memory User+Role for email-mapped identities not yet in the DB."""
    role = Role()
    role.id = f"synthetic-{role_name.lower()}"
    role.name = role_name

    user = User()
    user.id = user_id
    user.username = username
    user.email = email
    user.is_active = True
    user.role_id = role.id
    user.role = role
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials

    try:
        payload = decode_token(token)
    except TokenExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except TokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Path 1: look up by user_id in the database.
    # Fetch regardless of is_active so we can explicitly reject inactive users
    # rather than silently falling through to the email-map path.
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.role))
    )
    db_user = result.scalar_one_or_none()

    if db_user is not None:
        if not db_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return db_user

    # Path 2: email-mapped identity (not in DB).
    # Token must carry an email claim; role is re-validated against USER_ROLE_MAP
    # so that removing an email from the map immediately revokes access.
    email = payload.get("email", "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_name = get_role_for_email(email)
    if not role_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("username") or email.split("@")[0]
    return _synthetic_user(user_id, username, email, role_name)
