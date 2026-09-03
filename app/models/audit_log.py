import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_finding_id", "finding_id"),
        Index("ix_audit_logs_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)  # No FK for demo - stores email directly
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. UPDATE_STATUS
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. FINDING
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    finding_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("findings.id", ondelete="SET NULL"), nullable=True
    )
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Removed user relationship - users table doesn't exist in demo
    # user: Mapped["User"] = relationship("User", back_populates="audit_logs")  # noqa: F821
    finding: Mapped[Optional["Finding"]] = relationship(
        "Finding", back_populates="audit_logs"
    )  # noqa: F821

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action} resource_id={self.resource_id}>"
