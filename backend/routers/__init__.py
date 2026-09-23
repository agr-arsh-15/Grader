from backend.routers.auth import router as auth_router
from backend.routers.admin import router as admin_router
from backend.routers.candidate import router as candidate_router
from backend.routers.internal import router as internal_router

__all__ = ["auth_router", "admin_router", "candidate_router", "internal_router"]
