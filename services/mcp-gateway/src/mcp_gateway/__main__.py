"""Container and local entry point: `kosha-serve` or `python -m mcp_gateway`."""

import uvicorn

from mcp_gateway.settings import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "mcp_gateway.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        proxy_headers=True,
        server_header=False,
    )


if __name__ == "__main__":
    main()
