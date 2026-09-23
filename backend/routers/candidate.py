"""Candidate router: assignment listing, zip download, and submission upload."""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies import require_candidate, require_candidate_page
from backend.models.assignment import Assignment
from backend.models.submission import Submission, SubmissionStatus
from backend.models.user import User
from backend.services.file_service import (
    get_assignment_zip_path,
    save_log_file,
    save_submission_code,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ─────────────────────────────────────────────
# PAGE ROUTES
# ─────────────────────────────────────────────

@router.get("/candidate/dashboard", response_class=HTMLResponse)
async def candidate_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_candidate_page),
):
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(
        select(Submission)
        .options(selectinload(Submission.assignment))
        .where(Submission.candidate_id == user.id)
        .order_by(Submission.created_at.desc())
    )
    submissions = result.scalars().all()

    return templates.TemplateResponse(
        "candidate/dashboard.html",
        {"request": request, "user": user, "submissions": submissions},
    )


@router.get("/candidate/submissions/{submission_id}/submit", response_class=HTMLResponse)
async def submit_page(
    request: Request,
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_candidate_page),
):
    if isinstance(user, RedirectResponse):
        return user

    submission = await _get_candidate_submission(submission_id, user.id, db)

    return templates.TemplateResponse(
        "candidate/submit.html",
        {"request": request, "user": user, "submission": submission, "error": None},
    )


@router.post("/candidate/submissions/{submission_id}/submit")
async def upload_submission(
    request: Request,
    submission_id: uuid.UUID,
    code_zip: UploadFile = File(...),
    log_files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_candidate_page),
):
    if isinstance(user, RedirectResponse):
        return user

    submission = await _get_candidate_submission(submission_id, user.id, db)

    # Enforce due date
    now = datetime.now(timezone.utc)
    due = submission.due_at.replace(tzinfo=timezone.utc) if submission.due_at.tzinfo is None else submission.due_at
    if now > due:
        return templates.TemplateResponse(
            "candidate/submit.html",
            {
                "request": request,
                "user": user,
                "submission": submission,
                "error": f"The submission deadline passed on {due.strftime('%Y-%m-%d %H:%M UTC')}. No further uploads are accepted.",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if submission.status not in (SubmissionStatus.pending, SubmissionStatus.submitted):
        return templates.TemplateResponse(
            "candidate/submit.html",
            {
                "request": request,
                "user": user,
                "submission": submission,
                "error": f"Cannot upload: submission is in '{submission.status.value}' state.",
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    try:
        code_path = await save_submission_code(code_zip, submission_id)
        log_paths = []
        for i, lf in enumerate(log_files):
            if lf.filename:  # skip empty file inputs
                p = await save_log_file(lf, submission_id, i)
                log_paths.append(p)
    except HTTPException as exc:
        return templates.TemplateResponse(
            "candidate/submit.html",
            {"request": request, "user": user, "submission": submission, "error": exc.detail},
            status_code=exc.status_code,
        )

    submission.code_zip_path = code_path
    submission.log_file_paths = log_paths
    submission.status = SubmissionStatus.submitted
    submission.submitted_at = datetime.now(timezone.utc)
    await db.commit()

    return RedirectResponse(url="/candidate/dashboard", status_code=302)


# ─────────────────────────────────────────────
# FILE DOWNLOAD
# ─────────────────────────────────────────────

@router.get("/candidate/assignments/{assignment_id}/download")
async def download_assignment(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_candidate),
):
    """Serve assignment zip. Only accessible to candidates with an active submission."""
    # Verify candidate has a submission for this assignment
    sub_result = await db.execute(
        select(Submission).where(
            Submission.candidate_id == user.id,
            Submission.assignment_id == assignment_id,
        )
    )
    if sub_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this assignment",
        )

    asgn_result = await db.execute(
        select(Assignment).where(Assignment.id == assignment_id)
    )
    assignment = asgn_result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # CRITICAL: serve zip_file_path ONLY — never bug_manifest_path
    zip_path = get_assignment_zip_path(assignment.zip_file_path)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Assignment file not found on server")

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"{assignment.title.replace(' ', '_')}.zip",
    )


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

async def _get_candidate_submission(
    submission_id: uuid.UUID, candidate_id: uuid.UUID, db: AsyncSession
) -> Submission:
    result = await db.execute(
        select(Submission)
        .options(selectinload(Submission.assignment))
        .where(
            Submission.id == submission_id,
            Submission.candidate_id == candidate_id,
        )
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found or access denied",
        )
    return submission
