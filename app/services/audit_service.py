from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.audit_repository import AuditRepository


class AuditService:

    def __init__(self, session: AsyncSession):
        self._repo = AuditRepository(session)

    async def record_status_change(
        self,
        user_id: str,
        finding_id: str,
        old_status: str,
        new_status: str,
    ) -> AuditLog:
        return await self._repo.create(
            user_id=user_id,
            action="UPDATE_STATUS",
            resource_type="FINDING",
            resource_id=finding_id,
            old_value=old_status,
            new_value=new_status,
            finding_id=finding_id,
        )

    async def get_finding_history(self, finding_id: str) -> list[AuditLog]:
        return await self._repo.get_for_finding(finding_id)
