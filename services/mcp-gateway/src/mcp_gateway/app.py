"""ASGI application factory for Streamable HTTP."""

from starlette.applications import Starlette

from mcp_gateway.server import create_server
from mcp_gateway.settings import Settings


def create_app(settings: Settings | None = None) -> Starlette:
    """Stateless, JSON-response Streamable HTTP: safe behind Lambda and any load balancer."""
    settings = settings or Settings()
    return create_server().http_app(
        path=settings.mcp_path,
        stateless_http=True,
        json_response=True,
    )
