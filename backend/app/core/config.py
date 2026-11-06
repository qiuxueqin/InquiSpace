from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, PositiveInt, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INQUISPACE_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    data_dir: Path = BACKEND_DIR / "data"
    serve_frontend: bool = False
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"
    llm_api_key: SecretStr | None = None
    llm_base_url: AnyHttpUrl = "https://api.deepseek.com"
    llm_model: str = "deepseek-flash"
    llm_effort: Literal["low", "high", "max"] = "high"
    llm_max_output_tokens: PositiveInt = 16000

    # Engineering defaults only: later services must explicitly enforce these limits.
    max_sources_per_version: PositiveInt = 10
    max_upload_bytes: PositiveInt = 10 * 1024 * 1024
    max_pdf_pages: PositiveInt = 100
    model_timeout_seconds: PositiveInt = 60
    parse_timeout_seconds: PositiveInt = 60
    run_timeout_seconds: PositiveInt = 180
    run_max_steps: PositiveInt = 20
    confirmation_ttl_seconds: PositiveInt = 30 * 60
    model_max_concurrency: PositiveInt = 2
    sqlite_busy_timeout_ms: PositiveInt = 5000

    # Authentication/session policy. Cookie security is explicit so development can
    # use HTTP while production deployments can require HTTPS.
    session_cookie_name: str = "session"
    session_ttl_seconds: PositiveInt = 8 * 60 * 60
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_path: str = "/"
    allowed_origins: list[str] = Field(default_factory=list)

    # Adjustable classroom starting values, not inferred historical time anchors.
    default_subject: str = "历史"
    default_grade: str = "高中"
    default_duration_minutes: PositiveInt = 45
    default_max_turns: PositiveInt = 20

    @field_validator("llm_base_url")
    @classmethod
    def official_deepseek_endpoint(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https" or value.host != "api.deepseek.com":
            raise ValueError("llm_base_url must use the official DeepSeek HTTPS endpoint")
        return value

    @field_validator("default_subject", "default_grade")
    @classmethod
    def nonempty_classroom_default(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Classroom defaults must not be blank")
        return value

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "inquispace.db"
