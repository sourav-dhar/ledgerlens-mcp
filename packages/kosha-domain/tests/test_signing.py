"""Internal requests are signed by the gateway and verified by core-api."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kosha_domain.signing import (
    ACTOR,
    KB_CEILING,
    SIGNATURE,
    TIMESTAMP,
    SignatureError,
    SignedRequest,
    sign,
    verify,
)

KEY = b"k" * 32
OLD_KEY = b"o" * 32
NOW = 1_794_000_000

REQUEST = SignedRequest(
    method="GET",
    target="/v1/customers?name=ravi",
    actor="staff-0042",
    kb_ceiling="internal",
    body=b"",
)


def _headers(request: SignedRequest = REQUEST, key: bytes = KEY, at: int = NOW) -> dict[str, str]:
    return sign(key, request, timestamp=at)


def test_a_signed_request_verifies_and_names_its_principal() -> None:
    principal = verify([KEY], REQUEST.method, REQUEST.target, REQUEST.body, _headers(), now=NOW)

    assert (principal.actor, principal.kb_ceiling) == ("staff-0042", "internal")


def test_signing_sets_every_internal_header() -> None:
    headers = _headers()

    assert headers[ACTOR] == "staff-0042"
    assert headers[KB_CEILING] == "internal"
    assert headers[TIMESTAMP] == str(NOW)
    assert headers[SIGNATURE].startswith("v1=")


def test_a_request_without_a_ceiling_carries_no_ceiling_header() -> None:
    request = REQUEST._replace(kb_ceiling=None)
    headers = _headers(request)

    assert KB_CEILING not in headers
    assert verify([KEY], "GET", request.target, b"", headers, now=NOW).kb_ceiling is None


def test_header_names_are_matched_case_insensitively() -> None:
    lowered = {k.lower(): v for k, v in _headers().items()}

    assert verify([KEY], "GET", REQUEST.target, b"", lowered, now=NOW).actor == "staff-0042"


@pytest.mark.parametrize(
    ("header", "value"),
    [(ACTOR, "compliance-0001"), (KB_CEILING, "restricted"), (TIMESTAMP, str(NOW + 1))],
)
def test_changing_a_signed_header_breaks_the_signature(header: str, value: str) -> None:
    headers = _headers() | {header: value}

    with pytest.raises(SignatureError, match="signature"):
        verify([KEY], "GET", REQUEST.target, b"", headers, now=NOW)


def test_adding_a_ceiling_breaks_the_signature() -> None:
    headers = _headers(REQUEST._replace(kb_ceiling=None)) | {KB_CEILING: "restricted"}

    with pytest.raises(SignatureError):
        verify([KEY], "GET", REQUEST.target, b"", headers, now=NOW)


@pytest.mark.parametrize(
    ("method", "target", "body"),
    [
        ("POST", REQUEST.target, b""),
        ("GET", "/v1/customers?name=anil", b""),
        ("GET", "/v1/accounts", b""),
        ("GET", REQUEST.target, b'{"amount_paise": 100}'),
    ],
)
def test_a_signature_covers_the_method_target_and_body(
    method: str, target: str, body: bytes
) -> None:
    with pytest.raises(SignatureError, match="signature"):
        verify([KEY], method, target, body, _headers(), now=NOW)


def test_the_previous_key_still_verifies_during_rotation() -> None:
    headers = _headers(key=OLD_KEY)

    assert verify([KEY, OLD_KEY], "GET", REQUEST.target, b"", headers, now=NOW)


def test_an_unknown_key_does_not_verify() -> None:
    with pytest.raises(SignatureError, match="signature"):
        verify([KEY], "GET", REQUEST.target, b"", _headers(key=OLD_KEY), now=NOW)


def test_no_keys_verify_nothing() -> None:
    with pytest.raises(SignatureError, match="not configured"):
        verify([], "GET", REQUEST.target, b"", _headers(), now=NOW)


@pytest.mark.parametrize("skew", [-61, 61, -3600])
def test_a_request_outside_the_clock_window_is_rejected(skew: int) -> None:
    headers = _headers(at=NOW + skew)

    with pytest.raises(SignatureError, match="timestamp"):
        verify([KEY], "GET", REQUEST.target, b"", headers, now=NOW)


@pytest.mark.parametrize("skew", [-60, 0, 60])
def test_a_request_inside_the_clock_window_is_accepted(skew: int) -> None:
    assert verify([KEY], "GET", REQUEST.target, b"", _headers(at=NOW + skew), now=NOW)


@pytest.mark.parametrize("missing", [ACTOR, TIMESTAMP, SIGNATURE])
def test_a_missing_header_is_rejected(missing: str) -> None:
    headers = {k: v for k, v in _headers().items() if k != missing}

    with pytest.raises(SignatureError, match="missing"):
        verify([KEY], "GET", REQUEST.target, b"", headers, now=NOW)


@pytest.mark.parametrize(
    ("header", "value"),
    [(TIMESTAMP, "yesterday"), (SIGNATURE, "v0=abcd"), (SIGNATURE, "v1=not-hex"), (ACTOR, "")],
)
def test_a_malformed_header_is_rejected(header: str, value: str) -> None:
    with pytest.raises(SignatureError):
        verify([KEY], "GET", REQUEST.target, b"", _headers() | {header: value}, now=NOW)


def test_a_short_key_is_refused() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        sign(b"short", REQUEST, timestamp=NOW)


@given(
    actor=st.text(st.characters(codec="ascii", exclude_categories=["Cc"]), min_size=1),
    body=st.binary(),
)
def test_any_signed_request_verifies(actor: str, body: bytes) -> None:
    request = REQUEST._replace(actor=actor, body=body)

    principal = verify([KEY], "GET", request.target, body, _headers(request), now=NOW)

    assert principal.actor == actor
