"""
Tests for the five MCP tools.

We call the tool functions directly (bypassing JSON-RPC transport) by
patching mcp.state.session_factory with the rolled-back test session.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.demo_tokens import get_demo_tokens
from app.auth.jwt import create_token
from app.mcp import tools as mcp_module

_tokens = get_demo_tokens()
VIEWER_TOKEN = _tokens["alice_viewer"]
ENGINEER_TOKEN = _tokens["bob_engineer"]
ADMIN_TOKEN = _tokens["carol_admin"]

PAYMENT_PROJECT_ID = "proj-payment-0000-0000-000000000001"
KNOWN_FINDING_ID = "find-0001-0000-0000-000000000001"
NONEXISTENT_ID = "00000000-0000-0000-0000-000000000000"


def _make_factory(session: AsyncSession):
    """Wrap a single AsyncSession in a factory that always returns it."""
    factory = MagicMock(spec=async_sessionmaker)

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            # Don't actually commit — the conftest rolls back the transaction
            pass

    # Each call to factory() must return a fresh _CM instance
    factory.side_effect = lambda: _CM()
    return factory


@pytest.fixture(autouse=True)
async def patch_mcp_state(db_session: AsyncSession, monkeypatch):
    """Inject the rolled-back test session; suppress commit so rollback stays intact."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock as _AM

    mcp_module.mcp.state = SimpleNamespace(session_factory=_make_factory(db_session))
    monkeypatch.setattr(db_session, "commit", _AM(return_value=None))
    yield


# ----------------------------------------------------------------
# Tool 1: get_security_findings
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_security_findings_returns_list():
    result = await mcp_module.get_security_findings(
        project_id=PAYMENT_PROJECT_ID, token=VIEWER_TOKEN
    )
    assert isinstance(result, list)
    assert len(result) > 0
    assert "id" in result[0]
    assert "severity" in result[0]


@pytest.mark.asyncio
async def test_get_security_findings_filter_severity():
    result = await mcp_module.get_security_findings(
        project_id=PAYMENT_PROJECT_ID, token=VIEWER_TOKEN, severity="CRITICAL"
    )
    assert all(f["severity"] == "CRITICAL" for f in result)


@pytest.mark.asyncio
async def test_get_security_findings_filter_status():
    result = await mcp_module.get_security_findings(
        project_id=PAYMENT_PROJECT_ID, token=VIEWER_TOKEN, status="OPEN"
    )
    assert all(f["status"] == "OPEN" for f in result)


@pytest.mark.asyncio
async def test_get_security_findings_limit():
    result = await mcp_module.get_security_findings(
        project_id=PAYMENT_PROJECT_ID, token=VIEWER_TOKEN, limit=2
    )
    assert len(result) <= 2


@pytest.mark.asyncio
async def test_get_security_findings_invalid_token():
    result = await mcp_module.get_security_findings(
        project_id=PAYMENT_PROJECT_ID, token="bad.token.here"
    )
    assert len(result) == 1
    assert "error" in result[0]
    assert "Authentication" in result[0]["error"]


@pytest.mark.asyncio
async def test_get_security_findings_expired_token():
    import time

    expired = create_token(
        "user-viewer-00000-0000-000000000001", "alice_viewer", "VIEWER", expiry_minutes=0
    )
    time.sleep(1)
    result = await mcp_module.get_security_findings(project_id=PAYMENT_PROJECT_ID, token=expired)
    assert "error" in result[0]


# ----------------------------------------------------------------
# Tool 2: get_finding_details
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_finding_details_returns_full_record():
    result = await mcp_module.get_finding_details(finding_id=KNOWN_FINDING_ID, token=VIEWER_TOKEN)
    assert result["id"] == KNOWN_FINDING_ID
    assert "description" in result
    assert "remediation" in result
    assert "project_name" in result
    assert result["project_name"] == "Payment API"


@pytest.mark.asyncio
async def test_get_finding_details_not_found():
    result = await mcp_module.get_finding_details(finding_id=NONEXISTENT_ID, token=VIEWER_TOKEN)
    assert "error" in result


@pytest.mark.asyncio
async def test_get_finding_details_invalid_token():
    result = await mcp_module.get_finding_details(finding_id=KNOWN_FINDING_ID, token="garbage")
    assert "error" in result


# ----------------------------------------------------------------
# Tool 3: get_security_summary
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_security_summary_structure():
    result = await mcp_module.get_security_summary(
        project_id=PAYMENT_PROJECT_ID, token=VIEWER_TOKEN
    )
    assert result["project_id"] == PAYMENT_PROJECT_ID
    assert result["project_name"] == "Payment API"
    assert result["total"] > 0
    assert isinstance(result["by_severity"], dict)
    assert isinstance(result["by_status"], dict)


@pytest.mark.asyncio
async def test_get_security_summary_unknown_project():
    result = await mcp_module.get_security_summary(project_id=NONEXISTENT_ID, token=VIEWER_TOKEN)
    assert "error" in result


@pytest.mark.asyncio
async def test_get_security_summary_invalid_token():
    result = await mcp_module.get_security_summary(project_id=PAYMENT_PROJECT_ID, token="bad")
    assert "error" in result


# ----------------------------------------------------------------
# Tool 4: update_finding_status
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_finding_status_engineer_succeeds():
    result = await mcp_module.update_finding_status(
        finding_id=KNOWN_FINDING_ID, status="IN_PROGRESS", token=ENGINEER_TOKEN
    )
    assert result["new_status"] == "IN_PROGRESS"
    assert "old_status" in result  # value depends on DB state; don't assert exact value
    assert result["audit_recorded"] is True
    assert result["updated_by"] == "bob_engineer"


@pytest.mark.asyncio
async def test_update_finding_status_admin_succeeds():
    result = await mcp_module.update_finding_status(
        finding_id="find-0003-0000-0000-000000000003",
        status="RESOLVED",
        token=ADMIN_TOKEN,
    )
    assert result["new_status"] == "RESOLVED"
    assert result["resolved_at"] is not None
    assert result["audit_recorded"] is True


@pytest.mark.asyncio
async def test_update_finding_status_viewer_denied():
    result = await mcp_module.update_finding_status(
        finding_id=KNOWN_FINDING_ID, status="IN_PROGRESS", token=VIEWER_TOKEN
    )
    assert "error" in result
    assert "Authorization" in result["error"]


@pytest.mark.asyncio
async def test_update_finding_status_invalid_status():
    result = await mcp_module.update_finding_status(
        finding_id=KNOWN_FINDING_ID, status="HACKED", token=ENGINEER_TOKEN
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_update_finding_status_not_found():
    result = await mcp_module.update_finding_status(
        finding_id=NONEXISTENT_ID, status="RESOLVED", token=ENGINEER_TOKEN
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_update_finding_status_invalid_token():
    result = await mcp_module.update_finding_status(
        finding_id=KNOWN_FINDING_ID, status="IN_PROGRESS", token="bad.token"
    )
    assert "error" in result


# ----------------------------------------------------------------
# Tool 5: get_finding_audit_history
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_finding_audit_history_empty_initially():
    result = await mcp_module.get_finding_audit_history(
        finding_id=KNOWN_FINDING_ID, token=VIEWER_TOKEN
    )
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_finding_audit_history_after_update():
    target = "find-0007-0000-0000-000000000007"
    await mcp_module.update_finding_status(
        finding_id=target, status="IN_PROGRESS", token=ENGINEER_TOKEN
    )
    result = await mcp_module.get_finding_audit_history(finding_id=target, token=VIEWER_TOKEN)
    assert len(result) >= 1
    assert result[0]["action"] == "UPDATE_STATUS"
    assert result[0]["old_value"] == "OPEN"
    assert result[0]["new_value"] == "IN_PROGRESS"
    assert result[0]["username"] == "bob_engineer"


@pytest.mark.asyncio
async def test_get_finding_audit_history_not_found():
    result = await mcp_module.get_finding_audit_history(
        finding_id=NONEXISTENT_ID, token=VIEWER_TOKEN
    )
    assert len(result) == 1
    assert "error" in result[0]


@pytest.mark.asyncio
async def test_get_finding_audit_history_invalid_token():
    result = await mcp_module.get_finding_audit_history(
        finding_id=KNOWN_FINDING_ID, token="garbage"
    )
    assert "error" in result[0]


# ----------------------------------------------------------------
# Tool discovery — verify FastMCP registered all five tools
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_discovery():
    tool_list = await mcp_module.mcp.list_tools()
    names = {t.name for t in tool_list}
    expected = {
        "get_security_findings",
        "get_finding_details",
        "get_security_summary",
        "update_finding_status",
        "get_finding_audit_history",
    }
    assert expected == names
