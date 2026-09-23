import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class GradingResultIn(BaseModel):
    """Payload POSTed by the grading service to /api/internal/grading/result."""
    submission_id: uuid.UUID
    automated_score: float
    ai_usage_score: float
    overall_score: float
    per_bug_status: dict[str, str]  # bug_id -> "fixed" | "not_fixed" | "partial" | "not_automated"
    notes: Optional[str] = None


class GradingResultOut(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    automated_score: float
    ai_usage_score: float
    overall_score: float
    per_bug_status: dict[str, str]
    notes: Optional[str]
    graded_at: datetime

    model_config = {"from_attributes": True}
