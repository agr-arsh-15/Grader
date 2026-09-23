import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


_backend_env = Path(__file__).resolve().parent / ".env"
_root_env = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_backend_env, _root_env, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


    # Database (Defaults to SQLite for local/demo/serverless if not specified in env)
    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:////tmp/grader.db" if os.getenv("VERCEL") else "sqlite+aiosqlite:///./grader.db",
    )

    # JWT
    jwt_secret: str = os.getenv(
        "JWT_SECRET", "default_secret_key_grader_portal_must_be_changed_in_prod"
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Internal service communication
    internal_api_key: str = os.getenv(
        "INTERNAL_API_KEY", "default_internal_service_api_key_secret"
    )
    grading_service_url: str = "http://localhost:5100"
    backend_url: str = "http://localhost:8000"

    # File storage
    upload_dir: str = "/tmp/uploads" if os.getenv("VERCEL") else "uploads"
    max_upload_size_mb: int = 50

    # Seed admin (used only by seed.py)
    seed_admin_email: str = ""
    seed_admin_password: str = ""


settings = Settings()

