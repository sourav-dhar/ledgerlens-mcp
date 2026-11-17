"""Envelope encryption for PANs (ADR 0014, LLD security §4).

Each PAN is sealed with its own AES-256-GCM data key, and the data key is wrapped by a
``Keyring``: AWS KMS in production, ``LocalKeyring`` for local stacks and tests. Both
layers bind the Customer's ID as authenticated data, so a token copied onto another
Customer's row cannot be opened. A token is ``kms:v1:<wrapped key>.<nonce>.<ciphertext>``
in unpadded base64url, whichever keyring wrapped it.

Shared by the generator (which seals synthetic PANs) and ``core-api`` (which opens them for
the ``kyc:pii`` scope), so both agree on the format.
"""

import base64
import binascii
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

type RandBytes = Callable[[int], bytes]

LOCAL_PASSPHRASE = "kosha-local-only-pan-keyring"  # noqa: S105 — synthetic data only
"""The passphrase the generator seals synthetic PANs with and the local stack opens them with.

Synthetic data only: deployed environments use the KMS keyring, never this.
"""

_PREFIX = "kms:v1:"
_KEY_BYTES = 32
_NONCE_BYTES = 12


class VaultError(Exception):
    """A token could not be opened: damaged, foreign, or sealed under another key."""


class Keyring(Protocol):
    """Wraps and unwraps data keys; the part AWS KMS plays in production."""

    def generate_data_key(
        self, context: Mapping[str, str], randbytes: RandBytes
    ) -> tuple[bytes, bytes]:
        """A fresh plaintext data key and the same key wrapped under ``context``."""
        ...

    def decrypt_data_key(self, wrapped: bytes, context: Mapping[str, str]) -> bytes:
        """The plaintext data key, if ``wrapped`` was made under this keyring and ``context``."""
        ...


def _aad(context: Mapping[str, str]) -> bytes:
    return json.dumps(dict(context), sort_keys=True, separators=(",", ":")).encode()


class LocalKeyring:
    """A KMS stand-in for local stacks and tests: data keys wrapped by a passphrase-derived key.

    Not for real secrets: the key is a plain SHA-256 of the passphrase. It exists so the
    PAN path can be built and tested end to end before KMS is deployed (P6).
    """

    def __init__(self, passphrase: str) -> None:
        if not passphrase:
            msg = "a local keyring needs a passphrase"
            raise ValueError(msg)
        self._wrapping = AESGCM(hashlib.sha256(f"kosha-keyring:{passphrase}".encode()).digest())

    def generate_data_key(
        self, context: Mapping[str, str], randbytes: RandBytes
    ) -> tuple[bytes, bytes]:
        data_key = randbytes(_KEY_BYTES)
        nonce = randbytes(_NONCE_BYTES)
        return data_key, nonce + self._wrapping.encrypt(nonce, data_key, _aad(context))

    def decrypt_data_key(self, wrapped: bytes, context: Mapping[str, str]) -> bytes:
        nonce, sealed = wrapped[:_NONCE_BYTES], wrapped[_NONCE_BYTES:]
        return self._wrapping.decrypt(nonce, sealed, _aad(context))


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class PanVault:
    def __init__(self, keyring: Keyring) -> None:
        self._keyring = keyring

    @staticmethod
    def _context(customer_id: str) -> dict[str, str]:
        return {"purpose": "pan", "customer_id": customer_id}

    def encrypt(self, pan: str, *, customer_id: str, randbytes: RandBytes = os.urandom) -> str:
        """Seal ``pan`` for ``customer_id``.

        ``randbytes`` defaults to the OS generator; the synthetic-data generator passes its
        seeded one so a dataset stays reproducible.
        """
        context = self._context(customer_id)
        data_key, wrapped = self._keyring.generate_data_key(context, randbytes)
        nonce = randbytes(_NONCE_BYTES)
        sealed = AESGCM(data_key).encrypt(nonce, pan.encode(), _aad(context))
        return _PREFIX + ".".join(_encode(part) for part in (wrapped, nonce, sealed))

    def decrypt(self, token: str, *, customer_id: str) -> str:
        """The PAN sealed in ``token`` for ``customer_id``.

        Raises:
            VaultError: if the token is malformed, tampered with, sealed for another
                Customer or under another keyring.
        """
        if not token.startswith(_PREFIX):
            msg = "not a v1 PAN token"
            raise VaultError(msg)
        context = self._context(customer_id)
        try:
            wrapped, nonce, sealed = (_decode(p) for p in token.removeprefix(_PREFIX).split("."))
            data_key = self._keyring.decrypt_data_key(wrapped, context)
            return AESGCM(data_key).decrypt(nonce, sealed, _aad(context)).decode()
        except (InvalidTag, ValueError, binascii.Error) as exc:
            msg = "the PAN token cannot be opened for this Customer"
            raise VaultError(msg) from exc
