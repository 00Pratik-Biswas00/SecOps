from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.finding import Finding
from app.models.project import Project


class FindingRepository:

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, finding_id: str) -> Finding | None:
        result = await self._session.execute(
            select(Finding).where(Finding.id == finding_id).options(selectinload(Finding.project))
        )
        return result.scalar_one_or_none()

    async def list_findings(
        self,
        project_id: str,
        severity: str | None = None,
        status: str | None = None,
        scan_type: str | None = None,
        limit: int = 50,
    ) -> list[Finding]:
        stmt = (
            select(Finding)
            .where(Finding.project_id == project_id)
            .options(selectinload(Finding.project))
            .order_by(Finding.created_at.desc())
            .limit(min(limit, 200))
        )
        if severity:
            stmt = stmt.where(Finding.severity == severity.upper())
        if status:
            stmt = stmt.where(Finding.status == status.upper())
        if scan_type:
            stmt = stmt.where(Finding.scan_type == scan_type.upper())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_project_summary(self, project_id: str) -> dict:
        total_stmt = select(func.count()).where(Finding.project_id == project_id)
        total = (await self._session.execute(total_stmt)).scalar_one()

        by_severity_stmt = (
            select(Finding.severity, func.count())
            .where(Finding.project_id == project_id)
            .group_by(Finding.severity)
        )
        by_severity: dict[str, int] = {
            row[0]: row[1] for row in (await self._session.execute(by_severity_stmt)).all()
        }

        by_status_stmt = (
            select(Finding.status, func.count())
            .where(Finding.project_id == project_id)
            .group_by(Finding.status)
        )
        by_status: dict[str, int] = {
            row[0]: row[1] for row in (await self._session.execute(by_status_stmt)).all()
        }

        project_stmt = select(Project).where(Project.id == project_id)
        project = (await self._session.execute(project_stmt)).scalar_one_or_none()

        return {
            "project_id": project_id,
            "project_name": project.name if project else None,
            "total": total,
            "by_severity": by_severity,
            "by_status": by_status,
        }

    async def update_status(self, finding: Finding, new_status: str) -> Finding:
        from datetime import datetime

        finding.status = new_status.upper()
        finding.updated_at = datetime.now(UTC)
        finding.resolved_at = datetime.now(UTC) if new_status.upper() == "RESOLVED" else None
        self._session.add(finding)
        return finding
