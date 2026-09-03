"""
Email-to-role resolver.

Reads USER_ROLE_MAP from .env:
  USER_ROLE_MAP=alice@example.com:VIEWER,bob@example.com:SECURITY_ENGINEER

Provides:
  get_role_for_email(email) -> str | None
"""

from app.config import get_settings
from app.services.authorization_service import _ROLE_PERMISSIONS

_VALID_ROLES = set(_ROLE_PERMISSIONS.keys())


def _parse_role_map(raw: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not raw.strip():
        return mapping
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        email, _, role = entry.partition(":")
        email = email.strip().lower()
        role = role.strip().upper()
        if email and role in _VALID_ROLES:
            mapping[email] = role
    return mapping


def get_role_for_email(email: str) -> str | None:
    """Return the role assigned to this email, or None if not in the map."""
    settings = get_settings()
    mapping = _parse_role_map(settings.user_role_map)
    return mapping.get(email.strip().lower())


def list_mapped_emails() -> dict[str, str]:
    """Return the full email→role mapping (for display/debug)."""
    settings = get_settings()
    return _parse_role_map(settings.user_role_map)
