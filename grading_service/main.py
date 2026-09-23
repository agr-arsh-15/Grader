"""
Grading Service — FastAPI micro-service.

Receives grading requests from the backend, runs automated checks + LLM
AI-usage review, then POSTs the result back to the backend's internal endpoint.

Run with:
    uvicorn main:app --port 5100
"""
import logging
import os
import tempfile
import zipfile
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from grader import run_automated_checks
from log_parser import parse_log_files
from llm_reviewer import review_ai_usage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Grading Service", version="1.0.0")


class GradeRequest(BaseModel):
    submission_id: str
    code_zip_path: str
    log_file_paths: list[str]
    bug_manifest_path: str
    callback_url: str
    callback_api_key: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/grade", status_code=202)
async def grade(req: GradeRequest):
    """
    Accepts a grading request and processes it synchronously.
    On completion, POSTs the result to req.callback_url.
    Returns 202 Accepted immediately (but processing is synchronous for v1).
    """
    logger.info("Grading request received for submission %s", req.submission_id)

    # ── Validate inputs ────────────────────────────────────────────────────
    code_zip = Path(req.code_zip_path)
    if not code_zip.exists():
        raise HTTPException(400, f"Code zip not found: {req.code_zip_path}")

    manifest_path = Path(req.bug_manifest_path)
    if not manifest_path.exists():
        raise HTTPException(400, f"Bug manifest not found: {req.bug_manifest_path}")

    import json
    with open(manifest_path) as f:
        try:
            manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"Invalid bug manifest JSON: {e}") from e

    bugs = manifest.get("bugs", [])
    if not isinstance(bugs, list):
        raise HTTPException(400, "Bug manifest 'bugs' field must be a list")

    # ── Extract submission zip to temp dir ────────────────────────────────
    with tempfile.TemporaryDirectory(prefix="grading_") as tmpdir:
        try:
            with zipfile.ZipFile(code_zip, "r") as zf:
                # Guard against zip-slip
                for member in zf.namelist():
                    target = Path(tmpdir) / member
                    if not str(target.resolve()).startswith(str(Path(tmpdir).resolve())):
                        raise HTTPException(400, "Zip file contains unsafe paths (zip-slip)")
                zf.extractall(tmpdir)
        except zipfile.BadZipFile as e:
            raise HTTPException(400, f"Invalid zip file: {e}") from e

        # ── Step 1: Automated bug checks ──────────────────────────────────
        logger.info("Running automated checks on %d bugs", len(bugs))
        per_bug_status = run_automated_checks(tmpdir, bugs)

        # ── Step 2: Parse log files ───────────────────────────────────────
        log_summary = parse_log_files(req.log_file_paths)

        # ── Step 3: LLM review ────────────────────────────────────────────
        logger.info("Running LLM review of AI session logs")
        ai_score, notes = review_ai_usage(log_summary)

    # ── Compute scores ────────────────────────────────────────────────────
    fixed_count = sum(1 for v in per_bug_status.values() if v == "fixed")
    partial_count = sum(1 for v in per_bug_status.values() if v == "partial")
    total_bugs = len(bugs)

    if total_bugs > 0:
        automated_score = round(
            ((fixed_count + 0.5 * partial_count) / total_bugs) * 100, 2
        )
    else:
        automated_score = 0.0

    overall_score = round(0.70 * automated_score + 0.30 * ai_score, 2)

    result_payload = {
        "submission_id": req.submission_id,
        "automated_score": automated_score,
        "ai_usage_score": round(ai_score, 2),
        "overall_score": overall_score,
        "per_bug_status": per_bug_status,
        "notes": notes,
    }

    logger.info(
        "Grading complete — automated=%.1f ai=%.1f overall=%.1f",
        automated_score, ai_score, overall_score,
    )

    # ── POST result back to backend ───────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                req.callback_url,
                json=result_payload,
                headers={"X-Internal-Api-Key": req.callback_api_key},
            )
            resp.raise_for_status()
        logger.info("Result delivered to backend (status %s)", resp.status_code)
    except httpx.HTTPError as e:
        logger.error("Failed to deliver grading result to backend: %s", e)
        raise HTTPException(502, f"Failed to deliver result to backend: {e}") from e

    return {"status": "graded", "submission_id": req.submission_id}
