"""Sign test requests the way the gateway signs its calls to core-api (ADR 0013)."""

import time
from collections.abc import Generator

import httpx

from kosha_domain.signing import SignedRequest, sign

TEST_KEY = "test-signing-key-" + "x" * 16
"""A throwaway key, at least 32 bytes, configured into the apps under test."""


class SignedAs(httpx.Auth):
    """An httpx auth flow that signs each request for one principal."""

    requires_request_body = True

    def __init__(
        self,
        actor: str,
        kb_ceiling: str | None = None,
        *,
        key: str = TEST_KEY,
        skew_s: int = 0,
    ) -> None:
        self._actor = actor
        self._kb_ceiling = kb_ceiling
        self._key = key.encode()
        self._skew_s = skew_s

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        signed = SignedRequest(
            method=request.method,
            target=request.url.raw_path.decode("ascii"),
            actor=self._actor,
            kb_ceiling=self._kb_ceiling,
            body=request.content,
        )
        request.headers.update(sign(self._key, signed, timestamp=int(time.time()) + self._skew_s))
        yield request
