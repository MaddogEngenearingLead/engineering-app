from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "engineering-pid-api"
    environment: str = "development"
    api_prefix: str = "/api"
    upload_dir: str = "backend/uploads"
    max_upload_size_mb: int = 25
    cors_origins: list[str] = ["*"]

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()


settings = Settings()
