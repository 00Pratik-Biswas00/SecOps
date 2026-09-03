"""
MCP tools — five focused operations over the security findings connector.

Each tool accepts a `token` argument (Bearer JWT) for authentication.
The token is validated, the user resolved, RBAC enforced, then the
appropriate service method is called.  No database logic lives here.
"""

from types import SimpleNamespace
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.api.schemas import FindingStatus, ScanType, Severity
from app.auth.email_role import get_role_for_email
from app.auth.jwt import TokenError, decode_token
from app.config import get_settings
from app.database import _build_database_url
from app.models.role import Role
from app.models.user import User
from app.services.finding_service import FindingNotFoundError, FindingService

settings = get_settings()

# ---------------------------------------------------------------------------
# FastMCP server instance.
# Tests can replace mcp.state.session_factory directly (see conftest).
# ---------------------------------------------------------------------------

mcp = FastMCP("enterprise-security-connector")

# FastMCP does not declare .state in its type stubs; we attach it as a plain
# namespace so tests can inject a rolled-back session without touching the engine.
mcp.state = SimpleNamespace(session_factory=None)  # type: ignore[attr-defined]


async def _get_factory() -> async_sessionmaker:
    """Return the session factory, initialising it lazily if needed."""
    state = mcp.state  # type: ignore[attr-defined]
    if state.session_factory is None:
        # Use _build_database_url() so Cloud Run's CLOUD_SQL_CONNECTION_NAME
        # env var is respected — same logic as app/database.py uses.
        engine = create_async_engine(_build_database_url(), echo=False, pool_pre_ping=True)
        state.session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return state.session_factory


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _synthetic_user(user_id: str, username: str, email: str, role_name: str) -> User:
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


async def _resolve_user(session: AsyncSession, token: str) -> User:
    try:
        payload = decode_token(token)
    except TokenError as e:
        raise ValueError(f"Authentication failed: {e}") from e

    user_id: str = payload.get("sub") or ""
    if not user_id:
        raise ValueError("Authentication failed: token missing subject claim.")
    result = await session.execute(
        select(User)
        .where(User.id == user_id, User.is_active == True)  # noqa: E712
        .options(selectinload(User.role))
    )
    user = result.scalar_one_or_none()
    if user:
        return user

    # Fallback: email-mapped identity not yet in DB
    email = payload.get("email", "").strip().lower()
    if not email:
        raise ValueError("Authentication failed: user not found.")
    role_name = get_role_for_email(email)
    if not role_name:
        raise ValueError("Authentication failed: user not authorised.")
    username = payload.get("username") or email.split("@")[0]
    return _synthetic_user(user_id, username, email, role_name)


def _err(msg: str) -> dict:
    return {"error": msg}


# ---------------------------------------------------------------------------
# Tool 1 — get_security_findings
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_security_findings(
    project_id: str,
    token: str,
    severity: str | None = None,
    status: str | None = None,
    scan_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return security findings for a project. Supports filtering by severity, status, and scan_type."""
    limit = max(1, min(limit, 200))

    # Validate and normalise optional filter inputs — return clear error to
    # Gemini rather than silently returning empty results for bad values
    if severity:
        valid_severities = {s.value for s in Severity}
        severity = severity.strip().upper()
        if severity not in valid_severities:
            return [
                _err(f"Invalid severity '{severity}'. Must be one of: {sorted(valid_severities)}")
            ]
    if status:
        valid_statuses = {s.value for s in FindingStatus}
        status = status.strip().upper()
        if status not in valid_statuses:
            return [_err(f"Invalid status '{status}'. Must be one of: {sorted(valid_statuses)}")]
    if scan_type:
        valid_scan_types = {s.value for s in ScanType}
        scan_type = scan_type.strip().upper()
        if scan_type not in valid_scan_types:
            return [
                _err(f"Invalid scan_type '{scan_type}'. Must be one of: {sorted(valid_scan_types)}")
            ]

    factory = await _get_factory()
    async with factory() as session:
        try:
            await _resolve_user(session, token)
        except ValueError as e:
            return [_err(str(e))]

        svc = FindingService(session)
        findings = await svc.get_findings(
            project_id=project_id,
            severity=severity,
            status=status,
            scan_type=scan_type,
            limit=limit,
        )

    return [
        {
            "id": f.id,
            "title": f.title,
            "severity": f.severity,
            "status": f.status,
            "scan_type": f.scan_type,
            "file_path": f.file_path,
            "line_number": f.line_number,
            "rule_id": f.rule_id,
            "created_at": f.created_at.isoformat(),
            "updated_at": f.updated_at.isoformat(),
            "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
        }
        for f in findings
    ]


# ---------------------------------------------------------------------------
# Tool 2 — get_finding_details
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_finding_details(
    finding_id: str,
    token: str,
) -> dict[str, Any]:
    """Return full details for a single finding including description and remediation guidance."""
    factory = await _get_factory()
    async with factory() as session:
        try:
            await _resolve_user(session, token)
        except ValueError as e:
            return _err(str(e))

        svc = FindingService(session)
        try:
            finding = await svc.get_finding(finding_id)
        except FindingNotFoundError:
            return _err(f"Finding '{finding_id}' not found.")

    return {
        "id": finding.id,
        "project_id": finding.project_id,
        "project_name": finding.project.name if finding.project else None,
        "title": finding.title,
        "description": finding.description,
        "severity": finding.severity,
        "status": finding.status,
        "scan_type": finding.scan_type,
        "file_path": finding.file_path,
        "line_number": finding.line_number,
        "rule_id": finding.rule_id,
        "remediation": finding.remediation,
        "created_at": finding.created_at.isoformat(),
        "updated_at": finding.updated_at.isoformat(),
        "resolved_at": finding.resolved_at.isoformat() if finding.resolved_at else None,
    }


# ---------------------------------------------------------------------------
# Tool 3 — get_security_summary
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_security_summary(
    project_id: str,
    token: str,
) -> dict[str, Any]:
    """Return an aggregated security summary for a project: total findings, counts by severity and status."""
    factory = await _get_factory()
    async with factory() as session:
        try:
            await _resolve_user(session, token)
        except ValueError as e:
            return _err(str(e))

        svc = FindingService(session)
        summary = await svc.get_summary(project_id)

    if summary["project_name"] is None:
        return _err(f"Project '{project_id}' not found.")

    return summary


# ---------------------------------------------------------------------------
# Tool 4 — update_finding_status
# ---------------------------------------------------------------------------


@mcp.tool()
async def update_finding_status(
    finding_id: str,
    status: str,
    token: str,
) -> dict[str, Any]:
    """
    Update the status of a finding. Requires SECURITY_ENGINEER or SECURITY_ADMIN role.
    Valid statuses: OPEN, IN_PROGRESS, RESOLVED.
    Every successful update creates an immutable audit record.
    """
    factory = await _get_factory()
    async with factory() as session:
        try:
            actor = await _resolve_user(session, token)
        except ValueError as e:
            return _err(str(e))

        svc = FindingService(session)
        try:
            current = await svc.get_finding(finding_id)
            old_status = current.status
            finding = await svc.update_status(finding_id, status, actor=actor)
            await session.commit()
        except FindingNotFoundError:
            return _err(f"Finding '{finding_id}' not found.")
        except PermissionError as e:
            return _err(f"Authorization denied: {e}")
        except ValueError as e:
            return _err(str(e))

    return {
        "finding_id": finding.id,
        "old_status": old_status,
        "new_status": finding.status,
        "updated_by": actor.username,
        "updated_at": finding.updated_at.isoformat(),
        "resolved_at": finding.resolved_at.isoformat() if finding.resolved_at else None,
        "audit_recorded": True,
    }


# ---------------------------------------------------------------------------
# Tool 5 — get_finding_audit_history
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_finding_audit_history(
    finding_id: str,
    token: str,
) -> list[dict[str, Any]]:
    """Return the complete audit history for a finding: who changed it, when, and what changed."""
    factory = await _get_factory()
    async with factory() as session:
        try:
            await _resolve_user(session, token)
        except ValueError as e:
            return [_err(str(e))]

        svc = FindingService(session)
        try:
            logs = await svc.get_audit_history(finding_id)
        except FindingNotFoundError:
            return [_err(f"Finding '{finding_id}' not found.")]

    return [
        {
            "id": log.id,
            "action": log.action,
            "username": log.user.username if log.user else "unknown",
            "old_value": log.old_value,
            "new_value": log.new_value,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]
