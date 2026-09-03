from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finding import Finding
from app.models.user import User
from app.repositories.finding_repository import FindingRepository
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationService


class FindingNotFoundError(Exception):
    pass


class FindingService:

    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = FindingRepository(session)
        self._audit = AuditService(session)
        self._authz = AuthorizationService()

    async def get_findings(
        self,
        project_id: str,
        severity: str | None = None,
        status: str | None = None,
        scan_type: str | None = None,
        limit: int = 50,
    ) -> list[Finding]:
        return await self._repo.list_findings(
            project_id=project_id,
            severity=severity,
            status=status,
            scan_type=scan_type,
            limit=limit,
        )

    async def get_finding(self, finding_id: str) -> Finding:
        finding = await self._repo.get_by_id(finding_id)
        if not finding:
            raise FindingNotFoundError(f"Finding '{finding_id}' not found.")
        return finding

    async def get_summary(self, project_id: str) -> dict:
        return await self._repo.get_project_summary(project_id)

    async def update_status(
        self,
        finding_id: str,
        new_status: str,
        actor: User,
    ) -> Finding:
        # RBAC check
        self._authz.require(actor, "update_finding")

        # Validate status value
        validated_status = AuthorizationService.validate_status(new_status)

        # Load finding
        finding = await self._repo.get_by_id(finding_id)
        if not finding:
            raise FindingNotFoundError(f"Finding '{finding_id}' not found.")

        old_status = finding.status

        # No-op guard
        if old_status == validated_status:
            return finding

        # Transactional update
        await self._repo.update_status(finding, validated_status)

        # Mandatory audit record
        await self._audit.record_status_change(
            user_id=actor.id,
            finding_id=finding_id,
            old_status=old_status,
            new_status=validated_status,
        )

        await self._session.flush()
        return finding

    async def get_audit_history(self, finding_id: str) -> list:
        # Verify finding exists first
        finding = await self._repo.get_by_id(finding_id)
        if not finding:
            raise FindingNotFoundError(f"Finding '{finding_id}' not found.")
        return await self._audit.get_finding_history(finding_id)
