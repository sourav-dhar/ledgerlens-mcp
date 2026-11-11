"""The container entry point starts uvicorn with the app factory and environment settings."""

import pytest

from screening_sim.__main__ import main


class FakeUvicornRun:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


@pytest.fixture
def uvicorn_run(monkeypatch: pytest.MonkeyPatch) -> FakeUvicornRun:
    fake = FakeUvicornRun()
    monkeypatch.setattr("uvicorn.run", fake)
    return fake


def test_main_runs_factory_with_environment_settings(
    monkeypatch: pytest.MonkeyPatch, uvicorn_run: FakeUvicornRun
) -> None:
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("LOG_LEVEL", "warning")

    main()

    [(args, kwargs)] = uvicorn_run.calls
    assert args == ("screening_sim.app:create_app",)
    assert kwargs["factory"] is True
    assert (kwargs["host"], kwargs["port"], kwargs["log_level"]) == ("0.0.0.0", 8080, "warning")
    assert kwargs["server_header"] is False


def test_main_defaults_to_loopback(
    monkeypatch: pytest.MonkeyPatch, uvicorn_run: FakeUvicornRun
) -> None:
    for name in ("HOST", "PORT", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)

    main()

    [(_, kwargs)] = uvicorn_run.calls
    assert (kwargs["host"], kwargs["port"]) == ("127.0.0.1", 8002)
