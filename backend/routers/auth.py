"""Auth router: login page (GET), login action (POST), logout (POST)."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import User
from backend.services.auth_service import create_access_token, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # If already logged in, redirect appropriately
    token = request.cookies.get("access_token")
    if token:
        from backend.services.auth_service import decode_token
        payload = decode_token(token)
        if payload:
            role = payload.get("role")
            return RedirectResponse(
                url="/admin/dashboard" if role == "admin" else "/candidate/dashboard",
                status_code=302,
            )
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/auth/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid email or password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_access_token(user.id, user.email, user.role)
    redirect_url = "/admin/dashboard" if user.role.value == "admin" else "/candidate/dashboard"
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings_expire(),
        path="/",
    )
    return response


@router.post("/auth/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("access_token", path="/")
    return response


def settings_expire() -> int:
    from backend.config import settings
    return settings.jwt_expire_minutes * 60
