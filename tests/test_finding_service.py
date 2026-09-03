import pytest

from app.services.authorization_service import AuthorizationService
from app.services.finding_service import FindingNotFoundError, FindingService

PAYMENT_PROJECT_ID = "proj-payment-0000-0000-000000000001"
IDENTITY_PROJECT_ID = "proj-identity-000-0000-000000000002"
KNOWN_FINDING_ID = "find-0001-0000-0000-000000000001"
NONEXISTENT_ID = "00000000-0000-0000-0000-000000000000"


# ----------------------------------------------------------------
# get_findings
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_findings_returns_list(db_session):
    svc = FindingService(db_session)
    findings = await svc.get_findings(project_id=PAYMENT_PROJECT_ID)
    assert len(findings) > 0


@pytest.mark.asyncio
async def test_get_findings_filter_severity(db_session):
    svc = FindingService(db_session)
    findings = await svc.get_findings(project_id=PAYMENT_PROJECT_ID, severity="CRITICAL")
    assert all(f.severity == "CRITICAL" for f in findings)


@pytest.mark.asyncio
async def test_get_findings_filter_status(db_session):
    svc = FindingService(db_session)
    findings = await svc.get_findings(project_id=PAYMENT_PROJECT_ID, status="OPEN")
    assert all(f.status == "OPEN" for f in findings)


@pytest.mark.asyncio
async def test_get_findings_filter_scan_type(db_session):
    svc = FindingService(db_session)
    findings = await svc.get_findings(project_id=PAYMENT_PROJECT_ID, scan_type="SAST")
    assert all(f.scan_type == "SAST" for f in findings)


@pytest.mark.asyncio
async def test_get_findings_limit(db_session):
    svc = FindingService(db_session)
    findings = await svc.get_findings(project_id=PAYMENT_PROJECT_ID, limit=2)
    assert len(findings) <= 2


@pytest.mark.asyncio
async def test_get_findings_empty_project(db_session):
    svc = FindingService(db_session)
    findings = await svc.get_findings(project_id=NONEXISTENT_ID)
    assert findings == []


# ----------------------------------------------------------------
# get_finding
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_finding_known(db_session):
    svc = FindingService(db_session)
    finding = await svc.get_finding(KNOWN_FINDING_ID)
    assert finding.id == KNOWN_FINDING_ID
    assert finding.severity == "CRITICAL"


@pytest.mark.asyncio
async def test_get_finding_not_found(db_session):
    svc = FindingService(db_session)
    with pytest.raises(FindingNotFoundError):
        await svc.get_finding(NONEXISTENT_ID)


# ----------------------------------------------------------------
# get_summary
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_summary_structure(db_session):
    svc = FindingService(db_session)
    summary = await svc.get_summary(PAYMENT_PROJECT_ID)
    assert summary["project_id"] == PAYMENT_PROJECT_ID
    assert summary["project_name"] == "Payment API"
    assert summary["total"] > 0
    assert isinstance(summary["by_severity"], dict)
    assert isinstance(summary["by_status"], dict)


# ----------------------------------------------------------------
# update_status — authorization
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_viewer_denied(db_session, user_viewer):
    svc = FindingService(db_session)
    with pytest.raises(PermissionError):
        await svc.update_status(KNOWN_FINDING_ID, "IN_PROGRESS", actor=user_viewer)


@pytest.mark.asyncio
async def test_update_status_engineer_allowed(db_session, user_engineer):
    svc = FindingService(db_session)
    finding = await svc.update_status(KNOWN_FINDING_ID, "IN_PROGRESS", actor=user_engineer)
    assert finding.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_update_status_admin_allowed(db_session, user_admin):
    svc = FindingService(db_session)
    # Use a different finding to avoid conflict with engineer test in same session
    finding = await svc.update_status(
        "find-0003-0000-0000-000000000003", "IN_PROGRESS", actor=user_admin
    )
    assert finding.status == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_update_status_sets_resolved_at(db_session, user_engineer):
    svc = FindingService(db_session)
    finding = await svc.update_status(
        "find-0005-0000-0000-000000000005", "RESOLVED", actor=user_engineer
    )
    assert finding.status == "RESOLVED"
    assert finding.resolved_at is not None


@pytest.mark.asyncio
async def test_update_status_clears_resolved_at(db_session, user_engineer):
    svc = FindingService(db_session)
    # First resolve it
    await svc.update_status("find-0004-0000-0000-000000000004", "RESOLVED", actor=user_engineer)
    # Then re-open it
    finding = await svc.update_status(
        "find-0004-0000-0000-000000000004", "OPEN", actor=user_engineer
    )
    assert finding.resolved_at is None


@pytest.mark.asyncio
async def test_update_status_invalid_status(db_session, user_engineer):
    svc = FindingService(db_session)
    with pytest.raises(ValueError, match="Invalid status"):
        await svc.update_status(KNOWN_FINDING_ID, "BANANA", actor=user_engineer)


@pytest.mark.asyncio
async def test_update_status_finding_not_found(db_session, user_engineer):
    svc = FindingService(db_session)
    with pytest.raises(FindingNotFoundError):
        await svc.update_status(NONEXISTENT_ID, "RESOLVED", actor=user_engineer)


@pytest.mark.asyncio
async def test_update_status_creates_audit_record(db_session, user_engineer):
    svc = FindingService(db_session)
    await svc.update_status("find-0007-0000-0000-000000000007", "IN_PROGRESS", actor=user_engineer)
    history = await svc.get_audit_history("find-0007-0000-0000-000000000007")
    assert len(history) >= 1
    entry = history[0]
    assert entry.action == "UPDATE_STATUS"
    assert entry.old_value == "OPEN"
    assert entry.new_value == "IN_PROGRESS"
    assert entry.user_id == user_engineer.id


# ----------------------------------------------------------------
# get_audit_history
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_audit_history_not_found(db_session):
    svc = FindingService(db_session)
    with pytest.raises(FindingNotFoundError):
        await svc.get_audit_history(NONEXISTENT_ID)


@pytest.mark.asyncio
async def test_get_audit_history_empty_before_update(db_session):
    svc = FindingService(db_session)
    history = await svc.get_audit_history(KNOWN_FINDING_ID)
    assert isinstance(history, list)


# ----------------------------------------------------------------
# AuthorizationService unit tests
# ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_authz_viewer_cannot_update(user_viewer):
    authz = AuthorizationService()
    assert authz.can(user_viewer, "read_findings") is True
    assert authz.can(user_viewer, "update_finding") is False


@pytest.mark.asyncio
async def test_authz_engineer_can_update(user_engineer):
    authz = AuthorizationService()
    assert authz.can(user_engineer, "update_finding") is True


@pytest.mark.asyncio
async def test_authz_admin_can_update(user_admin):
    authz = AuthorizationService()
    assert authz.can(user_admin, "update_finding") is True


def test_validate_status_valid():
    assert AuthorizationService.validate_status("open") == "OPEN"
    assert AuthorizationService.validate_status("RESOLVED") == "RESOLVED"


def test_validate_status_invalid():
    with pytest.raises(ValueError):
        AuthorizationService.validate_status("HACKED")
