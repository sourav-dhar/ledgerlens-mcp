"""How the gateway signs internal requests and core-api verifies them (ADR 0013).

The gateway forwards the principal it authenticated in headers, and proves it sent them
with an HMAC-SHA256 over the request, keyed by a shared secret. The secret never travels;
the signature binds the principal to this method, target, body and moment, so a captured
request cannot be replayed later or edited to act for someone else.

It lives here, beside the domain types, because both services must agree on it byte for
byte. It is pure: the caller supplies the clock and the raw request parts.
"""

import hashlib
import hmac
from collections.abc import Mapping, Sequence
from typing import NamedTuple

from kosha_domain.vocabulary import Classification

ACTOR = "X-Kosha-Actor"
KB_CEILING = "X-Kosha-Kb-Ceiling"
TIMESTAMP = "X-Kosha-Timestamp"
SIGNATURE = "X-Kosha-Signature"

MAX_SKEW_S = 60
"""How far a request's timestamp may be from the verifier's clock, either way."""
MIN_KEY_BYTES = 32

_SCHEME = "v1"
_HEX_DIGEST_LENGTH = 64


class SignatureError(Exception):
    """The request is not provably from the gateway; the reason is safe to log."""


class SignedRequest(NamedTuple):
    """The parts of a request a signature covers, besides its timestamp.

    ``target`` is the path and query exactly as sent (percent-encoded), as in an HTTP
    request line.
    """

    method: str
    target: str
    actor: str
    kb_ceiling: str | None
    body: bytes


class Principal(NamedTuple):
    """Who a verified request acts for."""

    actor: str
    kb_ceiling: Classification | None


def _canonical(request: SignedRequest, timestamp: str) -> bytes:
    return "\n".join(
        [
            f"kosha-{_SCHEME}",
            timestamp,
            request.method.upper(),
            request.target,
            request.actor,
            request.kb_ceiling or "",
            hashlib.sha256(request.body).hexdigest(),
        ]
    ).encode()


def _mac(key: bytes, message: bytes) -> bytes:
    if len(key) < MIN_KEY_BYTES:
        msg = f"a signing key must be at least {MIN_KEY_BYTES} bytes"
        raise ValueError(msg)
    return hmac.new(key, message, hashlib.sha256).digest()


def sign(key: bytes, request: SignedRequest, *, timestamp: int) -> dict[str, str]:
    """The headers that carry ``request``'s principal and prove the gateway sent it."""
    stamp = str(timestamp)
    headers = {
        ACTOR: request.actor,
        TIMESTAMP: stamp,
        SIGNATURE: f"{_SCHEME}={_mac(key, _canonical(request, stamp)).hex()}",
    }
    if request.kb_ceiling is not None:
        headers[KB_CEILING] = request.kb_ceiling
    return headers


def _required(headers: Mapping[str, str], name: str) -> str:
    value = headers.get(name.lower())
    if value is None:
        msg = f"missing {name} header"
        raise SignatureError(msg)
    return value


def _signature(value: str) -> bytes:
    scheme, _, digest = value.partition("=")
    if scheme != _SCHEME or len(digest) != _HEX_DIGEST_LENGTH:
        msg = f"malformed {SIGNATURE} header"
        raise SignatureError(msg)
    try:
        return bytes.fromhex(digest)
    except ValueError:
        msg = f"malformed {SIGNATURE} header"
        raise SignatureError(msg) from None


def _ceiling(value: str | None) -> Classification | None:
    if value is None:
        return None
    try:
        return Classification(value)
    except ValueError:
        msg = f"malformed {KB_CEILING} header"
        raise SignatureError(msg) from None


def verify(
    keys: Sequence[bytes],
    method: str,
    target: str,
    body: bytes,
    headers: Mapping[str, str],
    *,
    now: int,
) -> Principal:
    """The principal a request acts for, if any of ``keys`` signed it within the window.

    ``keys`` holds the current key first and, during a rotation, the previous one.

    Raises:
        SignatureError: if no keys are configured, a header is missing or malformed, the
            timestamp is outside ``MAX_SKEW_S`` of ``now``, or no key produced the
            signature.
    """
    if not keys:
        msg = "request signing is not configured"
        raise SignatureError(msg)
    lowered = {k.lower(): v for k, v in headers.items()}
    actor = _required(lowered, ACTOR)
    stamp = _required(lowered, TIMESTAMP)
    claimed = _signature(_required(lowered, SIGNATURE))
    raw_ceiling = lowered.get(KB_CEILING.lower())
    if not actor:
        msg = f"empty {ACTOR} header"
        raise SignatureError(msg)
    if not stamp.isdigit():
        msg = f"malformed {TIMESTAMP} header"
        raise SignatureError(msg)
    if abs(now - int(stamp)) > MAX_SKEW_S:
        msg = f"timestamp is more than {MAX_SKEW_S}s from the server clock"
        raise SignatureError(msg)

    message = _canonical(SignedRequest(method, target, actor, raw_ceiling, body), stamp)
    # Every key is tried, so timing does not reveal which one matched.
    matches = [hmac.compare_digest(_mac(key, message), claimed) for key in keys]
    if not any(matches):
        msg = "signature does not match"
        raise SignatureError(msg)
    return Principal(actor=actor, kb_ceiling=_ceiling(raw_ceiling))
