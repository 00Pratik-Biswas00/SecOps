from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Enums — single source of truth for valid values, shared by REST + MCP
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class ScanType(str, Enum):
    SAST = "SAST"
    SECRETS = "SECRETS"
    DEPENDENCY = "DEPENDENCY"
    LINT = "LINT"


# ---------------------------------------------------------------------------
# Response schemas — validate outbound data before it reaches Gemini
# ---------------------------------------------------------------------------


class FindingSummary(BaseModel):
    id: str
    project_id: str
    title: str
    severity: str
    status: str
    scan_type: str
    file_path: str | None
    line_number: int | None
    rule_id: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class FindingDetail(FindingSummary):
    description: str | None
    remediation: str | None
    project_name: str | None = None

    model_config = {"from_attributes": True}


class ProjectSummaryResponse(BaseModel):
    project_id: str
    project_name: str | None
    total: int
    by_severity: dict[str, int]
    by_status: dict[str, int]


# ---------------------------------------------------------------------------
# Request schemas — enum constraint catches bad input at the API boundary
# ---------------------------------------------------------------------------


class UpdateStatusRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        # Normalise to uppercase so "resolved" == "RESOLVED"
        upper = v.strip().upper()
        valid = {s.value for s in FindingStatus}
        if upper not in valid:
            raise ValueError(f"status must be one of {sorted(valid)}, got '{v}'")
        return upper


class UpdateStatusResponse(BaseModel):
    finding_id: str
    old_status: str
    new_status: str
    updated_at: datetime
    resolved_at: datetime | None


# ---------------------------------------------------------------------------
# Audit schema
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    id: str
    user_id: str
    username: str
    action: str
    resource_type: str
    resource_id: str
    old_value: str | None
    new_value: str | None
    timestamp: datetime

    model_config = {"from_attributes": True}
