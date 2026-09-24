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

    @property
    def async_database_url(self) -> str:
        url = (self.database_url or "").strip()
        # Clean up any surrounding quotes from pasting in Vercel
        if (url.startswith('"') and url.endswith('"')) or (url.startswith("'") and url.endswith("'")):
            url = url[1:-1].strip()
        # Clean up accidental "DATABASE_URL=" prefix
        if url.startswith("DATABASE_URL="):
            url = url.split("=", 1)[1].strip().strip('"\'')

        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite:///"):
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

        # If password contains unescaped '@' (e.g. Graderdk@2026), URL parser fails with multiple '@'
        if "://" in url and url.count("@") > 1:
            scheme, rest = url.split("://", 1)
            auth_part, host_part = rest.rsplit("@", 1)
            if ":" in auth_part:
                user, password = auth_part.split(":", 1)
                password = password.replace("@", "%40")
                url = f"{scheme}://{user}:{password}@{host_part}"

        return url


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

    # Seed admin
    seed_admin_email: str = os.getenv("SEED_ADMIN_EMAIL", "admin@grader.ai")
    seed_admin_password: str = os.getenv("SEED_ADMIN_PASSWORD", "Default@123")



settings = Settings()

