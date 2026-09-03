from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ProjectSummaryResponse
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.finding_service import FindingService

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _finding_service(db: AsyncSession = Depends(get_db)) -> FindingService:
    return FindingService(db)


@router.get("/{project_id}/summary", response_model=ProjectSummaryResponse)
async def get_project_summary(
    project_id: str,
    svc: FindingService = Depends(_finding_service),
    _: User = Depends(get_current_user),
):
    summary = await svc.get_summary(project_id)
    if summary["project_name"] is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    return ProjectSummaryResponse(**summary)
