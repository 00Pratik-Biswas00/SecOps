import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.demo_tokens import get_demo_tokens
from app.database import get_db
from app.main import app

PAYMENT_PROJECT_ID = "proj-payment-0000-0000-000000000001"
IDENTITY_PROJECT_ID = "proj-identity-000-0000-000000000002"
KNOWN_FINDING_ID = "find-0010-0000-0000-000000000010"  # HIGH/OPEN/SAST Identity
NONEXISTENT_ID = "00000000-0000-0000-0000-000000000000"

_tokens = get_demo_tokens()
VIEWER_TOKEN = _tokens["alice_viewer"]
ENGINEER_TOKEN = _tokens["bob_engineer"]
ADMIN_TOKEN = _tokens["carol_admin"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Test client that shares the rolled-back session from conftest."""

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ----------------------------------------------------------------
# Health
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ----------------------------------------------------------------
# GET /api/v1/findings  — list
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_findings_requires_auth(client):
    r = await client.get(f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}")
    assert r.status_code == 401  # no bearer → HTTPBearer returns 401


@pytest.mark.asyncio
async def test_list_findings_invalid_token(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}",
        headers={"Authorization": "Bearer garbage.token.here"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_findings_returns_results(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert all(f["project_id"] == PAYMENT_PROJECT_ID for f in data)


@pytest.mark.asyncio
async def test_list_findings_filter_severity(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}&severity=CRITICAL",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    assert all(f["severity"] == "CRITICAL" for f in r.json())


@pytest.mark.asyncio
async def test_list_findings_filter_status(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}&status=OPEN",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    assert all(f["status"] == "OPEN" for f in r.json())


@pytest.mark.asyncio
async def test_list_findings_filter_scan_type(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}&scan_type=SAST",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    assert all(f["scan_type"] == "SAST" for f in r.json())


@pytest.mark.asyncio
async def test_list_findings_limit(client):
    r = await client.get(
        f"/api/v1/findings?project_id={PAYMENT_PROJECT_ID}&limit=2",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    assert len(r.json()) <= 2


@pytest.mark.asyncio
async def test_list_findings_unknown_project_empty(client):
    r = await client.get(
        f"/api/v1/findings?project_id={NONEXISTENT_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    assert r.json() == []


# ----------------------------------------------------------------
# GET /api/v1/findings/{finding_id}  — detail
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_finding_detail(client):
    r = await client.get(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == KNOWN_FINDING_ID
    assert "description" in data
    assert "remediation" in data
    assert "project_name" in data


@pytest.mark.asyncio
async def test_get_finding_404(client):
    r = await client.get(
        f"/api/v1/findings/{NONEXISTENT_ID}",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_finding_401(client):
    r = await client.get(f"/api/v1/findings/{KNOWN_FINDING_ID}")
    assert r.status_code == 401  # no bearer → HTTPBearer returns 401


# ----------------------------------------------------------------
# GET /api/v1/projects/{project_id}/summary
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_summary(client):
    r = await client.get(
        f"/api/v1/projects/{PAYMENT_PROJECT_ID}/summary",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == PAYMENT_PROJECT_ID
    assert data["project_name"] == "Payment API"
    assert data["total"] > 0
    assert "by_severity" in data
    assert "by_status" in data


@pytest.mark.asyncio
async def test_project_summary_404(client):
    r = await client.get(
        f"/api/v1/projects/{NONEXISTENT_ID}/summary",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 404


# ----------------------------------------------------------------
# PATCH /api/v1/findings/{finding_id}  — update status
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_engineer_succeeds(client):
    r = await client.patch(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        json={"status": "IN_PROGRESS"},
        headers=auth(ENGINEER_TOKEN),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["new_status"] == "IN_PROGRESS"
    assert data["finding_id"] == KNOWN_FINDING_ID
    assert "old_status" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_update_status_admin_succeeds(client):
    r = await client.patch(
        "/api/v1/findings/find-0009-0000-0000-000000000009",
        json={"status": "RESOLVED"},
        headers=auth(ADMIN_TOKEN),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["new_status"] == "RESOLVED"
    assert data["resolved_at"] is not None


@pytest.mark.asyncio
async def test_update_status_viewer_403(client):
    r = await client.patch(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        json={"status": "IN_PROGRESS"},
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_status_invalid_status_422(client):
    r = await client.patch(
        f"/api/v1/findings/{KNOWN_FINDING_ID}",
        json={"status": "BANANA"},
        headers=auth(ENGINEER_TOKEN),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_status_404(client):
    r = await client.patch(
        f"/api/v1/findings/{NONEXISTENT_ID}",
        json={"status": "RESOLVED"},
        headers=auth(ENGINEER_TOKEN),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_status_creates_audit(client):
    target = "find-0013-0000-0000-000000000013"
    await client.patch(
        f"/api/v1/findings/{target}",
        json={"status": "IN_PROGRESS"},
        headers=auth(ENGINEER_TOKEN),
    )
    r = await client.get(
        f"/api/v1/findings/{target}/audit",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) >= 1
    assert logs[0]["action"] == "UPDATE_STATUS"
    assert logs[0]["new_value"] == "IN_PROGRESS"


# ----------------------------------------------------------------
# GET /api/v1/findings/{finding_id}/audit
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_history_empty(client):
    r = await client.get(
        f"/api/v1/findings/{KNOWN_FINDING_ID}/audit",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_audit_history_404(client):
    r = await client.get(
        f"/api/v1/findings/{NONEXISTENT_ID}/audit",
        headers=auth(VIEWER_TOKEN),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_audit_history_401(client):
    r = await client.get(f"/api/v1/findings/{KNOWN_FINDING_ID}/audit")
    assert r.status_code == 401
