import time
from datetime import UTC

import pytest

from app.auth.demo_tokens import get_demo_tokens
from app.auth.jwt import (
    TokenExpiredError,
    TokenInvalidError,
    create_token,
    decode_token,
    extract_user_id,
)
from app.services.authorization_service import AuthorizationService

# ----------------------------------------------------------------
# Token creation + decode
# ----------------------------------------------------------------


def test_create_and_decode_token():
    token = create_token("uid-1", "alice", "VIEWER")
    payload = decode_token(token)
    assert payload["sub"] == "uid-1"
    assert payload["username"] == "alice"
    assert payload["role"] == "VIEWER"


def test_extract_user_id():
    token = create_token("uid-42", "bob", "SECURITY_ENGINEER")
    assert extract_user_id(token) == "uid-42"


def test_token_contains_expiry():
    token = create_token("uid-1", "alice", "VIEWER")
    payload = decode_token(token)
    assert "exp" in payload
    assert "iat" in payload


# ----------------------------------------------------------------
# Expired token
# ----------------------------------------------------------------


def test_expired_token_raises():
    token = create_token("uid-1", "alice", "VIEWER", expiry_minutes=0)
    # expiry_minutes=0 means exp == iat; sleep 1s to guarantee expiry
    time.sleep(1)
    with pytest.raises(TokenExpiredError):
        decode_token(token)


# ----------------------------------------------------------------
# Invalid tokens
# ----------------------------------------------------------------


def test_tampered_token_raises():
    token = create_token("uid-1", "alice", "VIEWER")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(TokenInvalidError):
        decode_token(tampered)


def test_garbage_token_raises():
    with pytest.raises(TokenInvalidError):
        decode_token("not.a.jwt")


def test_empty_token_raises():
    with pytest.raises(TokenInvalidError):
        decode_token("")


def test_wrong_secret_raises():
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    payload = {
        "sub": "uid-1",
        "username": "alice",
        "role": "VIEWER",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=60),
    }
    bad_token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
    with pytest.raises(TokenInvalidError):
        decode_token(bad_token)


# ----------------------------------------------------------------
# Demo tokens are valid and decodable
# ----------------------------------------------------------------


def test_demo_tokens_all_valid():
    tokens = get_demo_tokens()
    assert len(tokens) == 3
    for username, token in tokens.items():
        payload = decode_token(token)
        assert payload["username"] == username


def test_demo_token_roles():
    tokens = get_demo_tokens()
    payload_viewer = decode_token(tokens["alice_viewer"])
    payload_engineer = decode_token(tokens["bob_engineer"])
    payload_admin = decode_token(tokens["carol_admin"])
    assert payload_viewer["role"] == "VIEWER"
    assert payload_engineer["role"] == "SECURITY_ENGINEER"
    assert payload_admin["role"] == "SECURITY_ADMIN"


# ----------------------------------------------------------------
# RBAC matrix (pure, no DB needed)
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_rbac_viewer_read_allowed(user_viewer):
    authz = AuthorizationService()
    assert authz.can(user_viewer, "read_findings") is True
    assert authz.can(user_viewer, "read_audit") is True


@pytest.mark.asyncio
async def test_rbac_viewer_update_denied(user_viewer):
    authz = AuthorizationService()
    assert authz.can(user_viewer, "update_finding") is False


@pytest.mark.asyncio
async def test_rbac_engineer_full(user_engineer):
    authz = AuthorizationService()
    assert authz.can(user_engineer, "read_findings") is True
    assert authz.can(user_engineer, "update_finding") is True
    assert authz.can(user_engineer, "read_audit") is True


@pytest.mark.asyncio
async def test_rbac_admin_full(user_admin):
    authz = AuthorizationService()
    assert authz.can(user_admin, "read_findings") is True
    assert authz.can(user_admin, "update_finding") is True
    assert authz.can(user_admin, "read_audit") is True


@pytest.mark.asyncio
async def test_rbac_require_raises_for_viewer(user_viewer):
    authz = AuthorizationService()
    with pytest.raises(PermissionError, match="update_finding"):
        authz.require(user_viewer, "update_finding")


@pytest.mark.asyncio
async def test_rbac_require_passes_for_engineer(user_engineer):
    authz = AuthorizationService()
    authz.require(user_engineer, "update_finding")  # must not raise


# ----------------------------------------------------------------
# update_status end-to-end with real DB users
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_viewer_cannot_update_via_service(db_session, user_viewer):
    from app.services.finding_service import FindingService

    svc = FindingService(db_session)
    with pytest.raises(PermissionError):
        await svc.update_status(
            "find-0009-0000-0000-000000000009", "IN_PROGRESS", actor=user_viewer
        )


@pytest.mark.asyncio
async def test_engineer_can_update_via_service(db_session, user_engineer):
    from app.services.finding_service import FindingService

    svc = FindingService(db_session)
    finding = await svc.update_status(
        "find-0009-0000-0000-000000000009", "IN_PROGRESS", actor=user_engineer
    )
    assert finding.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_invalid_jwt_not_accepted():
    with pytest.raises(TokenInvalidError):
        decode_token("invalid.token.value")


@pytest.mark.asyncio
async def test_expired_jwt_not_accepted():
    token = create_token("uid-1", "alice", "VIEWER", expiry_minutes=0)
    time.sleep(1)
    with pytest.raises(TokenExpiredError):
        decode_token(token)
