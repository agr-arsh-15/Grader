"""FastAPI dependencies for authentication and authorization."""
import uuid
from typing import Optional, Union

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import User, UserRole
from backend.services.auth_service import decode_token


# ---------------------------------------------------------------------------
# API dependencies (return 401/403 JSON for API routes)
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id and not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")

    user = None
    if user_id:
        try:
            result = await db.execute(select(User).where(User.id == uuid.UUID(str(user_id))))
            user = result.scalar_one_or_none()
        except Exception:
            user = None

    if user is None and email:
        result = await db.execute(select(User).where(User.email == str(email).lower().strip()))
        user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def require_candidate(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.candidate:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Candidate access required"
        )
    return user


# ---------------------------------------------------------------------------
# Page dependencies (redirect to /login for browser-facing routes)
# ---------------------------------------------------------------------------

async def get_page_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Union[User, RedirectResponse]:
    """Returns the authenticated User, or a RedirectResponse to /login."""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    payload = decode_token(token)
    if payload is None:
        return RedirectResponse(url="/login", status_code=302)
    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id and not email:
        return RedirectResponse(url="/login", status_code=302)

    user = None
    if user_id:
        try:
            result = await db.execute(select(User).where(User.id == uuid.UUID(str(user_id))))
            user = result.scalar_one_or_none()
        except Exception:
            user = None

    if user is None and email:
        result = await db.execute(select(User).where(User.email == str(email).lower().strip()))
        user = result.scalar_one_or_none()

    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return user



async def require_admin_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Union[User, RedirectResponse]:
    user = await get_page_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def require_candidate_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Union[User, RedirectResponse]:
    user = await get_page_user(request, db)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != UserRole.candidate:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Candidate access required"
        )
    return user
