import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.user import User
    from backend.models.submission import Submission


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Path relative to UPLOAD_DIR: assignments/{id}/assignment.zip
    zip_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    # Path relative to UPLOAD_DIR: assignments/{id}/bug_manifest.json
    # NEVER exposed via candidate-facing endpoints.
    bug_manifest_path: Mapped[str] = mapped_column(Text, nullable=False)
    rubric_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=False
    )

    created_by_user: Mapped["User"] = relationship(
        "User", back_populates="assignments_created", lazy="select"
    )
    submissions: Mapped[list["Submission"]] = relationship(
        "Submission", back_populates="assignment", lazy="select", cascade="all, delete-orphan", passive_deletes=True
    )
