import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from backend.models.submission import SubmissionStatus


class AssignCandidatesRequest(BaseModel):
    candidate_emails: list[EmailStr]
    due_at: datetime


class SubmissionOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    assignment_id: uuid.UUID
    status: SubmissionStatus
    due_at: datetime
    submitted_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class SubmissionStatusOut(BaseModel):
    """Candidate-facing status — no scores, no file paths, no grading details."""
    id: uuid.UUID
    assignment_id: uuid.UUID
    status: SubmissionStatus
    due_at: datetime
    submitted_at: Optional[datetime]

    model_config = {"from_attributes": True}
