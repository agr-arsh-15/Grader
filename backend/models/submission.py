import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.user import User
    from backend.models.assignment import Assignment
    from backend.models.grading_result import GradingResult


class SubmissionStatus(str, enum.Enum):
    pending = "pending"
    submitted = "submitted"
    grading = "grading"
    graded = "graded"


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, name="submissionstatus"),
        nullable=False,
        default=SubmissionStatus.pending,
    )
    # Path relative to UPLOAD_DIR: submissions/{id}/code.zip  (null until uploaded)
    code_zip_path: Mapped[Optional[str]] = mapped_column(nullable=True, default=None)
    # JSONB list of paths relative to UPLOAD_DIR
    log_file_paths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    due_at: Mapped[datetime] = mapped_column(nullable=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=False
    )

    candidate: Mapped["User"] = relationship("User", back_populates="submissions", lazy="select")
    assignment: Mapped["Assignment"] = relationship(
        "Assignment", back_populates="submissions", lazy="select"
    )
    grading_result: Mapped[Optional["GradingResult"]] = relationship(
        "GradingResult", back_populates="submission", uselist=False, lazy="select"
    )
