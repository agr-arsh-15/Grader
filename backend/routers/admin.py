"""Admin router: pages + API endpoints for submissions dashboard, assignment library, and candidate management."""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    UploadFile,
    File,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.database import get_db
from backend.dependencies import require_admin, require_admin_page
from backend.models.assignment import Assignment
from backend.models.grading_result import GradingResult
from backend.models.submission import Submission, SubmissionStatus
from backend.models.user import User, UserRole
from backend.services.auth_service import hash_password
from backend.services.email_service import (

    compose_assessment_email_text,
    generate_candidate_default_password,
    generate_candidate_portal_email,
)


from backend.services.file_service import (
    get_assignment_zip_path,
    save_assignment_zip,
    save_bug_manifest,
)
from backend.services.grading_client import GradingServiceError, trigger_grading

router = APIRouter()
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))




# ─────────────────────────────────────────────
# 1. SUBMISSIONS DASHBOARD
# ─────────────────────────────────────────────

@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(
        select(Submission)
        .options(
            selectinload(Submission.candidate),
            selectinload(Submission.assignment),
            selectinload(Submission.grading_result),
        )
        .order_by(Submission.created_at.desc())
    )
    submissions = result.scalars().all()

    assignments_result = await db.execute(
        select(Assignment).order_by(Assignment.created_at.desc())
    )
    assignments = assignments_result.scalars().all()

    candidates_result = await db.execute(
        select(User).where(User.role == UserRole.candidate)
    )
    candidates = candidates_result.scalars().all()

    # Calculate statistics
    total_submissions = len(submissions)
    pending_count = sum(1 for s in submissions if s.status == SubmissionStatus.pending)
    submitted_count = sum(1 for s in submissions if s.status == SubmissionStatus.submitted)
    grading_count = sum(1 for s in submissions if s.status == SubmissionStatus.grading)
    graded_count = sum(1 for s in submissions if s.status == SubmissionStatus.graded)

    stats = {
        "total_submissions": total_submissions,
        "pending_count": pending_count,
        "submitted_count": submitted_count,
        "grading_count": grading_count,
        "graded_count": graded_count,
        "total_assignments": len(assignments),
        "total_candidates": len(candidates),
    }

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "user": user,
            "submissions": submissions,
            "assignments": assignments,
            "stats": stats,
            "active_page": "dashboard",
        },
    )



# ─────────────────────────────────────────────
# 2. CANDIDATE MANAGEMENT
# ─────────────────────────────────────────────

@router.get("/admin/candidates", response_class=HTMLResponse)
async def admin_candidates_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(
        select(User)
        .where(User.role == UserRole.candidate)
        .options(
            selectinload(User.submissions).selectinload(Submission.assignment),
            selectinload(User.submissions).selectinload(Submission.grading_result),
        )
        .order_by(User.created_at.desc())
    )
    candidates = result.scalars().all()

    assignments_result = await db.execute(
        select(Assignment).order_by(Assignment.title.asc())
    )
    assignments = assignments_result.scalars().all()

    return templates.TemplateResponse(
        "admin/candidates.html",
        {
            "request": request,
            "user": user,
            "candidates": candidates,
            "assignments": assignments,
            "error": None,
            "success": None,
            "new_credentials": None,
            "active_page": "candidates",
        },
    )


@router.post("/admin/candidates/create", response_class=HTMLResponse)
async def create_candidate(
    request: Request,
    full_name: str = Form(...),
    contact_email: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    cleaned_name = full_name.strip()
    cleaned_contact_email = contact_email.strip().lower()

    async def get_candidates_and_assignments():
        c_res = await db.execute(
            select(User)
            .where(User.role == UserRole.candidate)
            .options(
                selectinload(User.submissions).selectinload(Submission.assignment),
                selectinload(User.submissions).selectinload(Submission.grading_result),
            )
            .order_by(User.created_at.desc())
        )
        a_res = await db.execute(select(Assignment).order_by(Assignment.title.asc()))
        return c_res.scalars().all(), a_res.scalars().all()

    if not cleaned_name:
        candidates, assignments = await get_candidates_and_assignments()
        return templates.TemplateResponse(
            "admin/candidates.html",
            {
                "request": request,
                "user": user,
                "candidates": candidates,
                "assignments": assignments,
                "error": "Please enter the candidate's full name.",
                "success": None,
                "new_credentials": None,
                "active_page": "candidates",
            },
            status_code=400,
        )

    if not cleaned_contact_email or "@" not in cleaned_contact_email:
        candidates, assignments = await get_candidates_and_assignments()
        return templates.TemplateResponse(
            "admin/candidates.html",
            {
                "request": request,
                "user": user,
                "candidates": candidates,
                "assignments": assignments,
                "error": "Please enter a valid candidate contact email.",
                "success": None,
                "new_credentials": None,
                "active_page": "candidates",
            },
            status_code=400,
        )

    # Derive portal email: candidate_name@grader.com
    base_portal_email = generate_candidate_portal_email(cleaned_name)
    portal_email = base_portal_email
    suffix = 2

    # Check collisions
    while True:
        existing = await db.execute(select(User).where(User.email == portal_email))
        if existing.scalar_one_or_none() is None:
            break
        name_part, domain = base_portal_email.split("@")
        portal_email = f"{name_part}_{suffix}@{domain}"
        suffix += 1

    # Derive default password: Name@123
    portal_password = generate_candidate_default_password(cleaned_name)

    new_candidate = User(
        email=portal_email,
        full_name=cleaned_name,
        contact_email=cleaned_contact_email,
        password_hash=hash_password(portal_password),
        role=UserRole.candidate,
    )
    db.add(new_candidate)
    await db.commit()

    candidates, assignments = await get_candidates_and_assignments()

    new_credentials = {
        "full_name": cleaned_name,
        "contact_email": cleaned_contact_email,
        "email": portal_email,
        "password": portal_password,
    }

    return templates.TemplateResponse(
        "admin/candidates.html",
        {
            "request": request,
            "user": user,
            "candidates": candidates,
            "assignments": assignments,
            "error": None,
            "success": f"Candidate '{cleaned_name}' created successfully ({portal_email})!",
            "active_page": "candidates",
        },
    )



@router.post("/admin/candidates/{candidate_id}/delete", response_class=HTMLResponse)
async def delete_candidate(
    request: Request,
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    candidate = await db.get(User, candidate_id)
    if not candidate or candidate.role != UserRole.candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    deleted_email = candidate.email
    deleted_name = candidate.full_name or candidate.email

    await db.delete(candidate)
    await db.commit()

    c_res = await db.execute(
        select(User)
        .where(User.role == UserRole.candidate)
        .options(
            selectinload(User.submissions).selectinload(Submission.assignment),
            selectinload(User.submissions).selectinload(Submission.grading_result),
        )
        .order_by(User.created_at.desc())
    )
    candidates = c_res.scalars().all()
    a_res = await db.execute(select(Assignment).order_by(Assignment.title.asc()))
    assignments = a_res.scalars().all()

    return templates.TemplateResponse(
        "admin/candidates.html",
        {
            "request": request,
            "user": user,
            "candidates": candidates,
            "assignments": assignments,
            "error": None,
            "success": f"Candidate '{deleted_name}' ({deleted_email}) and all associated records deleted.",
            "new_credentials": None,
            "active_page": "candidates",
        },
    )


@router.post("/admin/candidates/{candidate_id}/edit", response_class=HTMLResponse)
async def edit_candidate(
    request: Request,
    candidate_id: uuid.UUID,
    full_name: str = Form(...),
    contact_email: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    candidate = await db.get(User, candidate_id)
    if not candidate or candidate.role != UserRole.candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    cleaned_name = full_name.strip()
    cleaned_contact_email = contact_email.strip().lower()

    async def get_candidates_and_assignments():
        c_res = await db.execute(
            select(User)
            .where(User.role == UserRole.candidate)
            .options(
                selectinload(User.submissions).selectinload(Submission.assignment),
                selectinload(User.submissions).selectinload(Submission.grading_result),
            )
            .order_by(User.created_at.desc())
        )
        a_res = await db.execute(select(Assignment).order_by(Assignment.title.asc()))
        return c_res.scalars().all(), a_res.scalars().all()

    if not cleaned_name:
        candidates, assignments = await get_candidates_and_assignments()
        return templates.TemplateResponse(
            "admin/candidates.html",
            {
                "request": request,
                "user": user,
                "candidates": candidates,
                "assignments": assignments,
                "error": "Please enter the candidate's full name.",
                "success": None,
                "new_credentials": None,
                "active_page": "candidates",
            },
            status_code=400,
        )

    if not cleaned_contact_email or "@" not in cleaned_contact_email:
        candidates, assignments = await get_candidates_and_assignments()
        return templates.TemplateResponse(
            "admin/candidates.html",
            {
                "request": request,
                "user": user,
                "candidates": candidates,
                "assignments": assignments,
                "error": "Please enter a valid candidate contact email.",
                "success": None,
                "new_credentials": None,
                "active_page": "candidates",
            },
            status_code=400,
        )

    candidate.full_name = cleaned_name
    candidate.contact_email = cleaned_contact_email
    await db.commit()

    candidates, assignments = await get_candidates_and_assignments()

    return templates.TemplateResponse(
        "admin/candidates.html",
        {
            "request": request,
            "user": user,
            "candidates": candidates,
            "assignments": assignments,
            "error": None,
            "success": f"Candidate profile '{cleaned_name}' updated successfully.",
            "new_credentials": None,
            "active_page": "candidates",
        },
    )


# ─────────────────────────────────────────────
# 3. ASSIGNMENTS LIBRARY & MANAGEMENT
# ─────────────────────────────────────────────

@router.get("/admin/assignments", response_class=HTMLResponse)
async def admin_assignments_library(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(
        select(Assignment)
        .options(
            selectinload(Assignment.created_by_user),
            selectinload(Assignment.submissions).selectinload(Submission.candidate),
            selectinload(Assignment.submissions).selectinload(Submission.grading_result),
        )
        .order_by(Assignment.created_at.desc())
    )
    assignments = result.scalars().all()

    return templates.TemplateResponse(
        "admin/assignments.html",
        {
            "request": request,
            "user": user,
            "assignments": assignments,
            "error": None,
            "success": None,
            "active_page": "assignments",
        },
    )


@router.get("/admin/assignments/create", response_class=HTMLResponse)
async def create_assignment_page(
    request: Request,
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(
        "admin/create_assignment.html",
        {"request": request, "user": user, "error": None, "active_page": "assignments"},
    )


@router.post("/admin/assignments/create")
async def create_assignment(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    rubric_text: str = Form(""),
    assignment_zip: UploadFile = File(...),
    bug_manifest: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    assignment_id = uuid.uuid4()
    try:
        zip_path = await save_assignment_zip(assignment_zip, assignment_id)
        manifest_path = await save_bug_manifest(bug_manifest, assignment_id)
    except HTTPException as exc:
        return templates.TemplateResponse(
            "admin/create_assignment.html",
            {"request": request, "user": user, "error": exc.detail, "active_page": "assignments"},
            status_code=exc.status_code,
        )

    assignment = Assignment(
        id=assignment_id,
        title=title,
        description=description,
        rubric_text=rubric_text,
        zip_file_path=zip_path,
        bug_manifest_path=manifest_path,
        created_by=user.id,
    )
    db.add(assignment)
    await db.commit()

    # Redirect directly back to Assignment Library
    return RedirectResponse(
        url="/admin/assignments",
        status_code=302,
    )


@router.get("/admin/assignments/{assignment_id}/edit", response_class=HTMLResponse)
async def edit_assignment_page(
    request: Request,
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    return templates.TemplateResponse(
        "admin/edit_assignment.html",
        {
            "request": request,
            "user": user,
            "assignment": assignment,
            "error": None,
            "active_page": "assignments",
        },
    )


@router.post("/admin/assignments/{assignment_id}/edit")
async def edit_assignment(
    request: Request,
    assignment_id: uuid.UUID,
    title: str = Form(...),
    description: str = Form(""),
    rubric_text: str = Form(""),
    assignment_zip: Optional[UploadFile] = File(None),
    bug_manifest: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assignment.title = title.strip()
    assignment.description = description.strip()
    assignment.rubric_text = rubric_text.strip()

    try:
        if assignment_zip and assignment_zip.filename:
            zip_path = await save_assignment_zip(assignment_zip, assignment_id)
            assignment.zip_file_path = zip_path

        if bug_manifest and bug_manifest.filename:
            manifest_path = await save_bug_manifest(bug_manifest, assignment_id)
            assignment.bug_manifest_path = manifest_path
    except HTTPException as exc:
        return templates.TemplateResponse(
            "admin/edit_assignment.html",
            {
                "request": request,
                "user": user,
                "assignment": assignment,
                "error": exc.detail,
                "active_page": "assignments",
            },
            status_code=exc.status_code,
        )

    await db.commit()

    return RedirectResponse(
        url="/admin/assignments",
        status_code=302,
    )


@router.get("/admin/assignments/{assignment_id}/download-zip")

async def download_assignment_zip(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    assignment = await db.get(Assignment, assignment_id)
    if not assignment or not assignment.zip_file_path:
        raise HTTPException(status_code=404, detail="Assignment codebase not found")

    full_path = get_assignment_zip_path(assignment.zip_file_path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    filename = f"{assignment.title.replace(' ', '_').lower()}_codebase.zip"
    return FileResponse(
        path=str(full_path),
        filename=filename,
        media_type="application/zip",
    )


@router.post("/admin/assignments/{assignment_id}/delete", response_class=HTMLResponse)
async def delete_assignment(
    request: Request,
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    title = assignment.title
    await db.delete(assignment)
    await db.commit()

    result = await db.execute(
        select(Assignment)
        .options(
            selectinload(Assignment.created_by_user),
            selectinload(Assignment.submissions).selectinload(Submission.candidate),
            selectinload(Assignment.submissions).selectinload(Submission.grading_result),
        )
        .order_by(Assignment.created_at.desc())
    )
    assignments = result.scalars().all()

    return templates.TemplateResponse(
        "admin/assignments.html",
        {
            "request": request,
            "user": user,
            "assignments": assignments,
            "error": None,
            "success": f"Assessment '{title}' deleted from library.",
            "active_page": "assignments",
        },
    )


@router.get("/admin/assignments/{assignment_id}/assign", response_class=HTMLResponse)
async def assign_candidates_page(
    request: Request,
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(select(Assignment).where(Assignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Only show candidates who do NOT currently have active assigned assignments (pending, submitted, grading)
    active_sub_subquery = (
        select(Submission.candidate_id)
        .where(Submission.status.in_([SubmissionStatus.pending, SubmissionStatus.submitted, SubmissionStatus.grading]))
    )
    candidates_result = await db.execute(
        select(User)
        .where(User.role == UserRole.candidate, ~User.id.in_(active_sub_subquery))
        .order_by(User.full_name.asc(), User.email.asc())
    )
    candidates = candidates_result.scalars().all()

    return templates.TemplateResponse(
        "admin/assign_candidates.html",
        {
            "request": request,
            "user": user,
            "assignment": assignment,
            "candidates": candidates,
            "error": None,
            "success": None,
            "assigned_cards": None,
            "active_page": "assignments",
        },
    )


@router.post("/admin/assignments/{assignment_id}/assign")
async def assign_candidates(
    request: Request,
    assignment_id: uuid.UUID,
    candidate_emails: list[str] = Form(...),
    due_at: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(select(Assignment).where(Assignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    active_sub_subquery = (
        select(Submission.candidate_id)
        .where(Submission.status.in_([SubmissionStatus.pending, SubmissionStatus.submitted, SubmissionStatus.grading]))
    )

    try:
        due_datetime = datetime.fromisoformat(due_at)
    except ValueError:
        candidates_result = await db.execute(
            select(User)
            .where(User.role == UserRole.candidate, ~User.id.in_(active_sub_subquery))
            .order_by(User.full_name.asc(), User.email.asc())
        )
        return templates.TemplateResponse(
            "admin/assign_candidates.html",
            {
                "request": request,
                "user": user,
                "assignment": assignment,
                "candidates": candidates_result.scalars().all(),
                "error": "Invalid due date format",
                "success": None,
                "assigned_cards": None,
                "active_page": "assignments",
            },
        )

    portal_url = str(request.base_url) + "login"
    due_date_str = due_datetime.strftime("%b %d, %Y %H:%M UTC")

    created = 0
    skipped = 0
    assigned_cards = []

    for email in candidate_emails:
        email = email.strip().lower()
        if not email:
            continue
        cand_result = await db.execute(select(User).where(User.email == email))
        candidate = cand_result.scalar_one_or_none()
        if candidate is None or candidate.role != UserRole.candidate:
            skipped += 1
            continue

        existing = await db.execute(
            select(Submission).where(
                Submission.candidate_id == candidate.id,
                Submission.assignment_id == assignment_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue

        sub = Submission(
            candidate_id=candidate.id,
            assignment_id=assignment_id,
            status=SubmissionStatus.pending,
            due_at=due_datetime,
            log_file_paths=[],
        )
        db.add(sub)
        created += 1

        candidate_name = candidate.full_name or candidate.email.split("@")[0]
    await db.commit()

    candidates_result = await db.execute(
        select(User)
        .where(User.role == UserRole.candidate, ~User.id.in_(active_sub_subquery))
        .order_by(User.full_name.asc(), User.email.asc())
    )
    return templates.TemplateResponse(
        "admin/assign_candidates.html",
        {
            "request": request,
            "user": user,
            "assignment": assignment,
            "candidates": candidates_result.scalars().all(),
            "error": None,
            "success": f"Successfully assigned assessment to {created} candidate(s)!",
            "active_page": "assignments",
        },
    )



# ─────────────────────────────────────────────
# 4. GRADING REPORTS & API
# ─────────────────────────────────────────────

@router.get("/admin/submissions/{submission_id}/report", response_class=HTMLResponse)
async def submission_report(
    request: Request,
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin_page),
):
    if isinstance(user, RedirectResponse):
        return user

    result = await db.execute(
        select(Submission)
        .options(
            selectinload(Submission.candidate),
            selectinload(Submission.assignment),
            selectinload(Submission.grading_result),
        )
        .where(Submission.id == submission_id)
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    return templates.TemplateResponse(
        "admin/report.html",
        {"request": request, "user": user, "submission": submission, "active_page": "dashboard"},
    )



@router.post("/api/admin/submissions/{submission_id}/grade")
async def trigger_grade(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = await db.execute(
        select(Submission)
        .options(selectinload(Submission.assignment))
        .where(Submission.id == submission_id)
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != SubmissionStatus.submitted:
        raise HTTPException(
            status_code=400,
            detail=f"Submission is in '{submission.status.value}' state; grading requires 'submitted'",
        )

    if not submission.code_zip_path:
        raise HTTPException(status_code=400, detail="Submission has no code zip uploaded")

    # Mark as grading
    submission.status = SubmissionStatus.grading
    await db.commit()

    try:
        await trigger_grading(
            submission_id=submission.id,
            code_zip_path=submission.code_zip_path,
            log_file_paths=submission.log_file_paths or [],
            bug_manifest_path=submission.assignment.bug_manifest_path,
        )
    except GradingServiceError as exc:
        submission.status = SubmissionStatus.submitted
        await db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return JSONResponse({"status": "grading_started", "submission_id": str(submission_id)})


@router.get("/api/admin/submissions")
async def list_submissions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = await db.execute(
        select(Submission).options(
            selectinload(Submission.candidate),
            selectinload(Submission.assignment),
        ).order_by(Submission.created_at.desc())
    )
    submissions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "candidate_email": s.candidate.email,
            "assignment_title": s.assignment.title,
            "status": s.status.value,
            "due_at": s.due_at.isoformat(),
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        }
        for s in submissions
    ]
