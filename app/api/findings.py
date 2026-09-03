from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AuditLogEntry,
    FindingDetail,
    FindingStatus,
    FindingSummary,
    ScanType,
    Severity,
    UpdateStatusRequest,
    UpdateStatusResponse,
)
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.finding_service import FindingNotFoundError, FindingService

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])


def _finding_service(db: AsyncSession = Depends(get_db)) -> FindingService:
    return FindingService(db)


@router.get("", response_model=list[FindingSummary])
async def list_findings(
    project_id: str = Query(..., description="Project UUID"),
    severity: Severity | None = Query(None, description="CRITICAL | HIGH | MEDIUM | LOW | INFO"),
    status: FindingStatus | None = Query(None, description="OPEN | IN_PROGRESS | RESOLVED"),
    scan_type: ScanType | None = Query(None, description="SAST | SECRETS | DEPENDENCY | LINT"),
    limit: int = Query(50, ge=1, le=200),
    svc: FindingService = Depends(_finding_service),
    _: User = Depends(get_current_user),
):
    findings = await svc.get_findings(
        project_id=project_id,
        severity=severity.value if severity else None,
        status=status.value if status else None,
        scan_type=scan_type.value if scan_type else None,
        limit=limit,
    )
    return [FindingSummary.model_validate(f) for f in findings]


@router.get("/{finding_id}", response_model=FindingDetail)
async def get_finding(
    finding_id: str,
    svc: FindingService = Depends(_finding_service),
    _: User = Depends(get_current_user),
):
    try:
        finding = await svc.get_finding(finding_id)
    except FindingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found.",
        ) from exc

    detail = FindingDetail.model_validate(finding)
    detail.project_name = finding.project.name if finding.project else None
    return detail


@router.patch("/{finding_id}", response_model=UpdateStatusResponse)
async def update_finding_status(
    finding_id: str,
    body: UpdateStatusRequest,
    svc: FindingService = Depends(_finding_service),
    actor: User = Depends(get_current_user),
):
    old_status: str = ""
    try:
        current = await svc.get_finding(finding_id)
        old_status = current.status
        finding = await svc.update_status(finding_id, body.status, actor=actor)
    except FindingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found.",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return UpdateStatusResponse(
        finding_id=finding.id,
        old_status=old_status,
        new_status=finding.status,
        updated_at=finding.updated_at,
        resolved_at=finding.resolved_at,
    )


@router.get("/{finding_id}/audit", response_model=list[AuditLogEntry])
async def get_finding_audit(
    finding_id: str,
    svc: FindingService = Depends(_finding_service),
    _: User = Depends(get_current_user),
):
    try:
        logs = await svc.get_audit_history(finding_id)
    except FindingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found.",
        ) from exc

    return [
        AuditLogEntry(
            id=log.id,
            user_id=log.user_id,
            username=log.user.username if log.user else "unknown",
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            old_value=log.old_value,
            new_value=log.new_value,
            timestamp=log.timestamp,
        )
        for log in logs
    ]
