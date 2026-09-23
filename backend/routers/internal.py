"""Internal router: receives grading results from the Python grading service.
Protected by a shared INTERNAL_API_KEY header — not JWT.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_db
from backend.models.grading_result import GradingResult
from backend.models.submission import Submission, SubmissionStatus
from backend.schemas.grading import GradingResultIn

router = APIRouter(prefix="/api/internal")


def _check_internal_key(x_internal_api_key: str = Header(...)) -> None:
    if x_internal_api_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )


@router.post("/grading/result", status_code=status.HTTP_201_CREATED)
async def receive_grading_result(
    payload: GradingResultIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_check_internal_key),
):
    # Verify submission exists
    result = await db.execute(
        select(Submission).where(Submission.id == payload.submission_id)
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission {payload.submission_id} not found",
        )

    # Upsert grading result (allow re-grading)
    existing = await db.execute(
        select(GradingResult).where(GradingResult.submission_id == payload.submission_id)
    )
    gr = existing.scalar_one_or_none()
    if gr is None:
        gr = GradingResult(submission_id=payload.submission_id)
        db.add(gr)

    gr.automated_score = payload.automated_score
    gr.ai_usage_score = payload.ai_usage_score
    gr.overall_score = payload.overall_score
    gr.per_bug_status = payload.per_bug_status
    gr.notes = payload.notes
    gr.graded_at = datetime.now(timezone.utc)

    # Flip submission status
    submission.status = SubmissionStatus.graded

    await db.commit()
    return {"status": "ok", "grading_result_id": str(gr.id)}
