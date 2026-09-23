from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # Internal service communication
    internal_api_key: str
    grading_service_url: str = "http://localhost:5100"
    backend_url: str = "http://localhost:8000"

    # File storage
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 50

    # Seed admin (used only by seed.py)
    seed_admin_email: str = ""
    seed_admin_password: str = ""


settings = Settings()
