"""FastAPI application factory."""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.config import settings
from backend.middleware.error_handler import ErrorHandlerMiddleware
from backend.routers import auth_router, admin_router, candidate_router, internal_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

app = FastAPI(
    title="AI Assessment Grading Portal",
    version="1.0.0",
    # Disable auto-generated docs in production by setting docs_url=None
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ── Middleware ──────────────────────────────────────────────────────────────
app.add_middleware(ErrorHandlerMiddleware)

# ── Static files & templates ────────────────────────────────────────────────
_static_dir = Path(__file__).parent / "static"
try:
    _static_dir.mkdir(exist_ok=True)
except OSError:
    pass

if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Ensure upload directory exists
try:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
except OSError:
    pass


@app.on_event("startup")
async def on_startup():
    from backend.database import init_db
    await init_db()




# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(candidate_router)
app.include_router(internal_router)


# ── Root redirect ────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/login", status_code=302)


# ── Global HTTPException handler (returns clean JSON) ───────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # If request expects HTML (browser navigation), return redirect for 401
    accept = request.headers.get("accept", "")
    if exc.status_code == 401 and "text/html" in accept:
        return RedirectResponse(url="/login", status_code=302)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "about:blank",
            "title": exc.__class__.__name__,
            "status": exc.status_code,
            "detail": exc.detail,
        },
    )
