"""HTTP client that calls the grading service and handles the result."""
import uuid

import httpx

from backend.config import settings
from backend.services.file_service import absolute_path


class GradingServiceError(Exception):
    pass


async def trigger_grading(
    submission_id: uuid.UUID,
    code_zip_path: str,
    log_file_paths: list[str],
    bug_manifest_path: str,
) -> None:
    """
    Sends a grading request to the Python grading service.
    The service will POST the result back to /api/internal/grading/result.
    Raises GradingServiceError on communication failure.
    """
    payload = {
        "submission_id": str(submission_id),
        "code_zip_path": absolute_path(code_zip_path),
        "log_file_paths": [absolute_path(p) for p in log_file_paths],
        "bug_manifest_path": absolute_path(bug_manifest_path),
        "callback_url": f"{settings.backend_url}/api/internal/grading/result",
        "callback_api_key": settings.internal_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.grading_service_url}/grade",
                json=payload,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise GradingServiceError(
            f"Grading service returned {e.response.status_code}: {e.response.text}"
        ) from e
    except httpx.RequestError as e:
        raise GradingServiceError(
            f"Could not reach grading service at {settings.grading_service_url}: {e}"
        ) from e
