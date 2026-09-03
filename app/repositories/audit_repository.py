from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit_log import AuditLog


class AuditRepository:

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        old_value: str | None = None,
        new_value: str | None = None,
        finding_id: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_value=old_value,
            new_value=new_value,
            finding_id=finding_id,
        )
        self._session.add(log)
        return log

    async def get_for_finding(self, finding_id: str) -> list[AuditLog]:
        result = await self._session.execute(
            select(AuditLog)
            .where(AuditLog.finding_id == finding_id)
            # Removed selectinload(AuditLog.user) - users table doesn't exist in demo
            .order_by(AuditLog.timestamp.desc())
        )
        return list(result.scalars().all())
