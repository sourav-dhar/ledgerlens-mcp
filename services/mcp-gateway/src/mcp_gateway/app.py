"""ASGI application factory for Streamable HTTP."""

from fastmcp import FastMCP
from starlette.applications import Starlette

from mcp_gateway.server import create_server
from mcp_gateway.settings import Settings


def serve_http(server: FastMCP, settings: Settings) -> Starlette:
    """``server`` over stateless, JSON-response Streamable HTTP: safe behind Lambda and any
    load balancer, since no request depends on an earlier one reaching the same instance."""
    return server.http_app(path=settings.mcp_path, stateless_http=True, json_response=True)


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings()
    return serve_http(create_server(settings), settings)
