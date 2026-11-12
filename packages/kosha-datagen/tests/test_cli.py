"""The seed command refuses to run without somewhere to put the data or a sane scale."""

import pytest

from kosha_datagen.__main__ import main


def test_seeding_needs_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(SystemExit, match="DATABASE_URL is not set"):
        main([])


@pytest.mark.parametrize("scale", ["0", "1.5", "-0.1"])
def test_a_scale_outside_zero_to_one_is_refused(
    monkeypatch: pytest.MonkeyPatch, scale: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

    with pytest.raises(ValueError, match="scale must be in"):
        main(["--scale", scale])
