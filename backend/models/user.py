import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.assignment import Assignment
    from backend.models.submission import Submission


class UserRole(str, enum.Enum):
    admin = "admin"
    candidate = "candidate"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="userrole"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=False
    )

    assignments_created: Mapped[list["Assignment"]] = relationship(
        "Assignment", back_populates="created_by_user", lazy="select"
    )
    submissions: Mapped[list["Submission"]] = relationship(
        "Submission", back_populates="candidate", lazy="select", cascade="all, delete-orphan", passive_deletes=True
    )
