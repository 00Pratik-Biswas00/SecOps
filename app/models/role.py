import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )  # VIEWER, SECURITY_ENGINEER, SECURITY_ADMIN
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Removed users relationship - users table doesn't exist in demo
    # users: Mapped[list["User"]] = relationship("User", back_populates="role")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name}>"
