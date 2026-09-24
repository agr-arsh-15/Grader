import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.submission import Submission


class GradingResult(Base):
    __tablename__ = "grading_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    automated_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    ai_usage_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    overall_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    # Cross-database compatible JSON column (JSONB on PostgreSQL, JSON on SQLite)
    per_bug_status: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    notes: Mapped[Optional[str]] = mapped_column(nullable=True, default=None)
    graded_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=False
    )

    submission: Mapped["Submission"] = relationship(
        "Submission", back_populates="grading_result", lazy="select"
    )

    @property
    def total_score(self) -> float:
        return self.overall_score
