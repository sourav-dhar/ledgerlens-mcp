"""Deterministic synthetic data for Kosha Financial.

`generate` turns a `GenerationConfig` into a stream of `Batch` objects: plain rows, one
tuple per database row, with no I/O. `load` copies that stream into a migrated database
and `reconcile` proves the ledger afterwards. The same seed and as-of date always produce
the same rows, and a smaller ``scale`` produces a prefix of the full dataset.
"""

from kosha_datagen.batch import Batch
from kosha_datagen.config import GenerationConfig
from kosha_datagen.dataset import generate

__all__ = ["Batch", "GenerationConfig", "generate"]
