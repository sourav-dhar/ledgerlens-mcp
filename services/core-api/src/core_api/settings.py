"""Runtime configuration, read from environment variables."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-level settings shared by every deployment target.

    `HOST` defaults to loopback; container images set `HOST=0.0.0.0`.
    `PORT` matches what the Lambda Web Adapter forwards to.
    """

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    host: str = "127.0.0.1"
    port: int = 8001
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"
