"""Runtime configuration, read from environment variables."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-level settings shared by every deployment target.

    `HOST` defaults to loopback; container images set `HOST=0.0.0.0`.
    `PORT` matches what the Lambda Web Adapter forwards to.

    Without `DATABASE_URL` the service still starts and answers liveness, but is not ready
    and answers every data route with `503`.
    """

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    host: str = "127.0.0.1"
    port: int = 8001
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"

    database_url: SecretStr | None = None
    """libpq URL of the login role; it must be a member of `db_role`."""
    db_role: str = "kosha_app"
    """Role every unit of work runs as, so grants and row-level security always apply."""
    db_pool_max_size: int = Field(default=2, ge=1)
    """Per process: Lambda runs one request per instance, so two leaves room for a probe."""
    db_pool_timeout_s: float = Field(default=2.0, gt=0)
    """How long a request waits for a connection before answering `503`."""
    db_statement_timeout_ms: int = Field(default=3_000, gt=0)
    """Server-side cap on any one statement; exceeding it answers `504`."""
