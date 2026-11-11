"""Container and local entry point: `kosha-serve` or `python -m core_api`."""

import uvicorn

from core_api.settings import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "core_api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        proxy_headers=True,
        server_header=False,
    )


if __name__ == "__main__":
    main()
