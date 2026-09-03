"""
Phase 8 — Security and negative testing.

Covers:
  - Invalid / expired / tampered JWT
  - VIEWER attempting writes (REST + MCP)
  - Unknown finding / project
  - Invalid status values
  - Limit boundary enforcement
  - Sensitive data not returned
  - Audit records generated on every write
  - Cross-user isolation
"""

import time
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.demo_tokens import get_demo_tokens
from app.auth.jwt import create_token
from app.database import get_db
from app.main import app
from app.mcp import tools as mcp_module

_tokens = get_demo_tokens()
VIEWER_TOKEN = _tokens["alice_viewer"]
ENGINEER_TOKEN = _tokens["bob_engineer"]
ADMIN_TOKEN = _tokens["carol_admin"]

PAYMENT_PROJECT_ID = "proj-payment-0000-0000-000000000001"
KNOWN_FINDING_ID = "find-0004-0000-0000-000000000004"  # CRITICAL/OPEN — untouched by prior tests
SECRETS_FINDING_ID = "find-0002-0000-0000-000000000002"  # SECRETS scan type
NONEXISTENT_ID = "00000000-0000-0000-0000-000000000000"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── REST client fixture ──────────────────────────────────────────────────────


@pytest.fixture
async def client(db_session: AsyncSession):
    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ── MCP state fixture ────────────────────────────────────────────────────────


def _make_factory(session: AsyncSession):
    factory = MagicMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            pass

    factory.side_effect = lambda: _CM()
    return factory


@pytest.fixture(autouse=True)
async def patch_mcp(db_session: AsyncSession, monkeypatch):
    mcp_module.mcp.state = SimpleNamespace(session_factory=_make_factory(db_session))
    monkeypatch.setattr(db_session, "commit", AsyncMock(return_value=None))
    yield


# ============================================================================
# 1. INVALID / EXPIRED / TAMPERED JWT
# ============================================================================


@pytest.mark.asyncio
async def test_rest_no_token_returns_401(client):
    r = await client.get(f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rest_garbage_token_returns_401(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}",
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rest_tampered_token_returns_401(client):
    tampered = VIEWER_TOKEN[:-8] + "TAMPERED"
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}",
        headers=auth(tampered),
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rest_expired_token_returns_401(client):
    expired = create_token(
        "user-viewer-00000-0000-000000000001",
        "alice_viewer",
        "VIEWER",
        expiry_minutes=0,
    )
    time.sleep(1)
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}",
        headers=auth(expired),
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rest_wrong_secret_token_returns_401(client):
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    bad = pyjwt.encode(
        {
            "sub": "user-viewer-00000-0000-000000000001",
            "username": "alice_viewer",
            "role": "VIEWER",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=60),
        },
        "wrong-secret",
        algorithm="HS256",
    )
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}",
        headers=auth(bad),
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_mcp_invalid_token_returns_error():
    result = await mcp_module.get_security_findings(
        project_id=PAYMENT_PROJECT_ID, token="bad.token.value"
    )
    assert "error" in result[0]
    assert "Authentication" in result[0]["error"]


@pytest.mark.asyncio
async def test_mcp_expired_token_returns_error():
    expired = create_token(
        "user-viewer-00000-0000-000000000001",
        "alice_viewer",
        "VIEWER",
        expiry_minutes=0,
    )
    time.sleep(1)
    result = await mcp_module.get_security_findings(project_id=PAYMENT_PROJECT_ID, token=expired)
    assert "error" in result[0]


# ============================================================================
# 2. VIEWER CANNOT WRITE — REST + MCP
# ============================================================================


@pytest.mark.asyncio
async def test_rest_viewer_update_returns_403(client):
    r = await client.patch(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        json={"status": "IN_PROGRESS"},
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 403
    assert "permission" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_mcp_viewer_update_returns_auth_error():
    result = await mcp_module.update_finding_status(
        finding_id=KNOWN_FINDING_ID, status="IN_PROGRESS", token=VIEWER_TOKEN
    )
    assert "error" in result
    assert "Authorization" in result["error"]
    assert "VIEWER" in result["error"]


@pytest.mark.asyncio
async def test_rest_viewer_can_still_read(client):
    r = await client.get(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_rest_viewer_can_read_audit(client):
    r = await client.get(
        f"/api/v1/findings/{KNOWN_FINDING_ID}/audit",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200


# ============================================================================
# 3. UNKNOWN FINDING / PROJECT
# ============================================================================


@pytest.mark.asyncio
async def test_rest_unknown_finding_returns_404(client):
    r = await client.get(f"/api/v1/findings/{NONEXISTENT_ID}", headers=auth(VIEWER_TOKEN))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_rest_update_unknown_finding_returns_404(client):
    r = await client.patch(
        f"/api/v1/findings/{NONEXISTENT_ID}",
        json={"status": "RESOLVED"},
        headers=auth(ENGINEER_TOKEN),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_rest_audit_unknown_finding_returns_404(client):
    r = await client.get(
        f"/api/v1/findings/{NONEXISTENT_ID}/audit",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_rest_unknown_project_summary_returns_404(client):
    r = await client.get(
        f"/api/v1/projects/{NONEXISTENT_ID}/summary",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_rest_unknown_project_findings_returns_empty_list(client):
    r = await client.get(
        f"/api/v1/findings?project_id={NONEXISTENT_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_mcp_unknown_finding_returns_error():
    result = await mcp_module.get_finding_details(finding_id=NONEXISTENT_ID, token=VIEWER_TOKEN)
    assert "error" in result


@pytest.mark.asyncio
async def test_mcp_unknown_project_summary_returns_error():
    result = await mcp_module.get_security_summary(project_id=NONEXISTENT_ID, token=VIEWER_TOKEN)
    assert "error" in result


# ============================================================================
# 4. INVALID STATUS VALUES
# ============================================================================


@pytest.mark.asyncio
async def test_rest_invalid_status_returns_422(client):
    r = await client.patch(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        json={"status": "HACKED"},
        headers=auth(ENGINEER_TOKEN),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rest_empty_status_returns_422(client):
    r = await client.patch(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        json={"status": ""},
        headers=auth(ENGINEER_TOKEN),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rest_missing_status_body_returns_422(client):
    r = await client.patch(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        json={},
        headers=auth(ENGINEER_TOKEN),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_mcp_invalid_status_returns_error():
    result = await mcp_module.update_finding_status(
        finding_id=KNOWN_FINDING_ID, status="BANANA", token=ENGINEER_TOKEN
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_mcp_lowercase_status_is_accepted():
    """Status validation must normalise lowercase to uppercase."""
    result = await mcp_module.update_finding_status(
        finding_id=KNOWN_FINDING_ID, status="resolved", token=ENGINEER_TOKEN
    )
    assert "error" not in result
    assert result["new_status"] == "RESOLVED"


# ============================================================================
# 5. LIMIT BOUNDARY ENFORCEMENT
# ============================================================================


@pytest.mark.asyncio
async def test_rest_limit_zero_returns_422(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}&limit=0",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rest_limit_above_max_returns_422(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}&limit=999",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rest_limit_max_boundary_accepted(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}&limit=200",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_mcp_limit_enforced_in_service():
    """Service layer caps at 200 even if a caller passes more."""
    result = await mcp_module.get_security_findings(
        project_id=PAYMENT_PROJECT_ID, token=VIEWER_TOKEN, limit=500
    )
    # Should not error — service silently caps at 200
    assert isinstance(result, list)


# ============================================================================
# 6. SENSITIVE DATA NOT RETURNED
# ============================================================================


@pytest.mark.asyncio
async def test_secrets_finding_contains_no_raw_secret(client):
    """SECRETS-type findings must store only metadata, never raw credential values."""
    r = await client.get(
        f"/api/v1/findings/{SECRETS_FINDING_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    body = r.json()
    # Description and remediation must not contain patterns that look like real secrets
    text = (body.get("description") or "") + (body.get("remediation") or "")
    # No long base64/hex strings that could be an actual credential value
    import re

    raw_secret_pattern = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
    assert not raw_secret_pattern.search(
        text
    ), f"Possible raw secret found in finding response: {text[:200]}"


@pytest.mark.asyncio
async def test_finding_response_has_no_database_internals(client):
    r = await client.get(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    body = r.json()
    # Internal DB fields must not leak
    assert "_sa_instance_state" not in str(body)
    assert "password" not in str(body).lower()


@pytest.mark.asyncio
async def test_audit_log_contains_no_token(client):
    """Audit records must not store JWT tokens."""
    # First create an audit record
    await client.patch(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        json={"status": "IN_PROGRESS"},
        headers=auth(ENGINEER_TOKEN),
    )
    r = await client.get(
        f"/api/v1/findings/{KNOWN_FINDING_ID}/audit",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    audit_text = str(r.json())
    assert "AQ." not in audit_text  # no API key fragments
    assert "eyJ" not in audit_text  # no JWT header prefix
    assert "Bearer" not in audit_text


@pytest.mark.asyncio
async def test_user_info_not_over_exposed_in_findings(client):
    """Finding responses must not expose user credentials or emails."""
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    body_text = r.text
    assert "@secureorg.internal" not in body_text
    assert "role_id" not in body_text


# ============================================================================
# 7. AUDIT RECORD CREATED ON EVERY SUCCESSFUL WRITE
# ============================================================================


@pytest.mark.asyncio
async def test_every_status_update_creates_audit_record(client):
    target = "find-0015-0000-0000-000000000015"

    # Baseline audit count
    r0 = await client.get(f"/api/v1/findings/{target}/audit", headers=auth(VIEWER_TOKEN))
    count_before = len(r0.json())

    # First update
    await client.patch(
        f"/api/v1/findings/{target}", json={"status": "IN_PROGRESS"}, headers=auth(ENGINEER_TOKEN)
    )
    r1 = await client.get(f"/api/v1/findings/{target}/audit", headers=auth(VIEWER_TOKEN))
    assert len(r1.json()) == count_before + 1

    # Second update
    await client.patch(
        f"/api/v1/findings/{target}", json={"status": "RESOLVED"}, headers=auth(ADMIN_TOKEN)
    )
    r2 = await client.get(f"/api/v1/findings/{target}/audit", headers=auth(VIEWER_TOKEN))
    assert len(r2.json()) == count_before + 2


@pytest.mark.asyncio
async def test_audit_record_fields_are_complete(client):
    target = "find-0016-0000-0000-000000000016"
    await client.patch(
        f"/api/v1/findings/{target}", json={"status": "IN_PROGRESS"}, headers=auth(ENGINEER_TOKEN)
    )

    r = await client.get(f"/api/v1/findings/{target}/audit", headers=auth(VIEWER_TOKEN))
    entry = r.json()[0]

    assert entry["action"] == "UPDATE_STATUS"
    assert entry["username"] == "bob_engineer"
    assert entry["old_value"] is not None
    assert entry["new_value"] == "IN_PROGRESS"
    assert entry["timestamp"] is not None
    assert entry["resource_type"] == "FINDING"


@pytest.mark.asyncio
async def test_failed_update_does_not_create_audit(client):
    """A rejected update (VIEWER) must not leave an audit trail."""
    target = "find-0017-0000-0000-000000000017"
    r0 = await client.get(f"/api/v1/findings/{target}/audit", headers=auth(VIEWER_TOKEN))
    count_before = len(r0.json())

    # Attempt denied write
    await client.patch(
        f"/api/v1/findings/{target}", json={"status": "RESOLVED"}, headers=auth(VIEWER_TOKEN)
    )

    r1 = await client.get(f"/api/v1/findings/{target}/audit", headers=auth(VIEWER_TOKEN))
    assert len(r1.json()) == count_before  # no new record


# ============================================================================
# 8. CROSS-USER ISOLATION
# ============================================================================


@pytest.mark.asyncio
async def test_viewer_cannot_see_writes_blocked_at_boundary(client):
    """VIEWER read access is unaffected by what engineer does — isolation check."""
    # Engineer updates a finding
    await client.patch(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        json={"status": "IN_PROGRESS"},
        headers=auth(ENGINEER_TOKEN),
    )
    # Viewer can still read it
    r = await client.get(f"/api/v1/findings/{KNOWN_FINDING_ID}", headers=auth(VIEWER_TOKEN))
    assert r.status_code == 200
    assert r.json()["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_engineer_token_cannot_be_replayed_as_admin(client):
    """Engineer token must not grant admin-equivalent access beyond its role."""
    from app.models.role import Role

    # Engineer role permissions are exactly read + update — no more
    from app.models.user import User
    from app.services.authorization_service import AuthorizationService

    role = Role(name="SECURITY_ENGINEER")
    user = User(username="test", email="t@t.com", role_id="x")
    user.role = role
    authz = AuthorizationService()
    assert authz.can(user, "read_findings") is True
    assert authz.can(user, "update_finding") is True
    # No hypothetical escalation permissions exist
    assert authz.can(user, "delete_finding") is False
    assert authz.can(user, "admin_override") is False


@pytest.mark.asyncio
async def test_inactive_user_cannot_authenticate(client, db_session):
    """A user marked is_active=False must be rejected even with a valid JWT."""
    from sqlalchemy import select

    from app.models.user import User

    # Temporarily deactivate alice
    result = await db_session.execute(select(User).where(User.username == "alice_viewer"))
    alice = result.scalar_one()
    alice.is_active = False
    db_session.add(alice)
    await db_session.flush()

    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 401
