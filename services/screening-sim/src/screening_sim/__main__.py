"""Container and local entry point: `kosha-serve` or `python -m screening_sim`."""

import uvicorn

from screening_sim.settings import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "screening_sim.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        proxy_headers=True,
        server_header=False,
    )


if __name__ == "__main__":
    main()
