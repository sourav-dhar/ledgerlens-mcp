"""Opaque, tamper-evident pagination cursors (LLD §5).

core-api pages by keyset: the caller passes back the last row's position. The gateway
never hands that position to a client bare. It signs it, with the hash of the query it
continues, the subject it was issued to and an expiry, so a client can neither edit a
position, nor reuse one with other filters, nor pass one to someone else.

    base64url(json({"v", "k", "q", "sub", "exp"})) + "." + base64url(hmac_sha256(...))

Cursors are tamper-evident, not secret: the position holds values the caller has already
seen. Keys rotate like ADR 0013's: the current key signs, and every configured key verifies.
"""

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kosha_domain.signing import MIN_KEY_BYTES
from mcp_gateway.errors import InvalidArgumentError

TTL_S = 15 * 60


class _Claims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    v: Literal[1]
    k: dict[str, str]
    q: str = Field(pattern=r"^[0-9a-f]{64}$")
    sub: str
    exp: int


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(text: str) -> bytes:
    """Raises ``ValueError`` for anything that is not unpadded base64url."""
    padded = (text + "=" * (-len(text) % 4)).encode("ascii")
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def query_hash(query: Mapping[str, Any]) -> str:
    """SHA-256 of the query's canonical JSON: key order and spacing do not matter."""
    canonical = json.dumps(query, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class Cursors:
    """Issues and opens cursors; ``keys`` holds the current key first."""

    def __init__(
        self,
        keys: Sequence[bytes],
        *,
        ttl_s: int = TTL_S,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not keys:
            msg = "at least one cursor key is required"
            raise ValueError(msg)
        if any(len(key) < MIN_KEY_BYTES for key in keys):
            msg = f"each cursor key must be at least {MIN_KEY_BYTES} bytes"
            raise ValueError(msg)
        self._keys = tuple(keys)
        self._ttl_s = ttl_s
        self._clock = clock

    def issue(self, position: Mapping[str, str], *, query: Mapping[str, Any], sub: str) -> str:
        claims = _Claims(
            v=1,
            k=dict(position),
            q=query_hash(query),
            sub=sub,
            exp=int(self._clock()) + self._ttl_s,
        )
        payload = _encode(claims.model_dump_json().encode())
        return f"{payload}.{_encode(self._mac(self._keys[0], payload))}"

    def open(self, cursor: str, *, query: Mapping[str, Any], sub: str) -> dict[str, str]:
        """The position ``cursor`` continues from, if it is ours, current and for this query.

        Raises:
            InvalidArgumentError: otherwise, saying why when the signature holds.
        """
        claims = self._verified(cursor)
        if self._clock() > claims.exp:
            msg = "the cursor has expired; start again without one"
            raise InvalidArgumentError(msg)
        if not hmac.compare_digest(claims.q, query_hash(query)):
            msg = "the cursor belongs to another query; pass the same filters, or none"
            raise InvalidArgumentError(msg)
        if claims.sub != sub:
            msg = "the cursor was issued to someone else"
            raise InvalidArgumentError(msg)
        return dict(claims.k)

    def _mac(self, key: bytes, payload: str) -> bytes:
        return hmac.new(key, payload.encode(), hashlib.sha256).digest()

    def _verified(self, cursor: str) -> _Claims:
        invalid = InvalidArgumentError("the cursor is not valid; start again without one")
        payload, dot, signature = cursor.partition(".")
        try:
            claimed = _decode(signature)
        except ValueError:
            raise invalid from None
        # Every key is tried, so timing does not reveal which one matched.
        matches = [hmac.compare_digest(self._mac(key, payload), claimed) for key in self._keys]
        if not dot or not any(matches):
            raise invalid
        try:
            return _Claims.model_validate_json(_decode(payload))
        except (ValueError, ValidationError):
            raise invalid from None
