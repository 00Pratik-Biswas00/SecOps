import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        Index("ix_findings_project_id", "project_id"),
        Index("ix_findings_severity", "severity"),
        Index("ix_findings_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="OPEN"
    )  # OPEN, IN_PROGRESS, RESOLVED
    scan_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # SAST, SECRETS, DEPENDENCY, LINT
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    line_number: Mapped[int | None] = mapped_column(nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="findings")  # noqa: F821
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="finding"
    )  # noqa: F821

    def __repr__(self) -> str:
        return f"<Finding id={self.id} severity={self.severity} status={self.status}>"
