"""Runtime configuration, read from environment variables. Every timeout is explicit."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from kosha_domain.signing import MIN_KEY_BYTES
from mcp_gateway.auth.scopes import Role


class Settings(BaseSettings):
    """Process-level settings.

    `HOST` defaults to loopback; container images set `HOST=0.0.0.0`.
    `PORT` matches what the Lambda Web Adapter forwards to.

    Without `INTERNAL_SIGNING_KEY` the gateway still starts and reports its own health, but
    every tool that needs core-api answers `dependency_unavailable`.
    """

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"
    mcp_path: str = "/mcp"

    core_api_url: str = "http://127.0.0.1:8001"
    core_api_connect_timeout_s: float = Field(default=1.0, gt=0)
    core_api_timeout_s: float = Field(default=4.0, gt=0)
    """Read, write and pool timeout: core-api's statement timeout (3 s) plus a margin."""
    core_api_attempts: int = Field(default=2, ge=1)
    """Attempts per call, counting the first: transient failures are retried once."""
    core_api_backoff_s: float = Field(default=0.1, ge=0)
    """Upper bound of the full-jitter pause before a retry."""

    internal_signing_key: SecretStr | None = None
    """The key requests to core-api are signed with (ADR 0013): core-api's current key."""

    machine_client_roles: dict[str, Role] = {}
    """Role of each service client that authenticates with client credentials (ADR 0016),
    as JSON: `{"e2e-runner": "demo_readonly"}`."""

    @field_validator("internal_signing_key")
    @classmethod
    def _key_is_long_enough(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode()) < MIN_KEY_BYTES:
            msg = f"the internal signing key must be at least {MIN_KEY_BYTES} bytes"
            raise ValueError(msg)
        return value
