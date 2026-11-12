"""One small dataset, generated once and shared by the row-stream tests."""

from datetime import date

import pytest

from kosha_datagen import Batch, GenerationConfig, generate

AS_OF = date(2026, 11, 12)
SMALL = GenerationConfig(as_of=AS_OF, seed=7, scale=0.03)


@pytest.fixture(scope="session")
def dataset() -> Batch:
    """150 Customers and everything they own, merged into one batch."""
    return Batch.merge(generate(SMALL))
