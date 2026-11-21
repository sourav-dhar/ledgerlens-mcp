"""Pagination cursors are opaque to clients and tamper-evident (LLD §5).

A cursor carries a keyset position, bound by an HMAC to the query it continues, the subject
it was issued to and an expiry. Anything else a client sends back is `invalid_argument`.
"""

import base64
import hashlib
import hmac
import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mcp_gateway.cursors import Cursors
from mcp_gateway.errors import InvalidArgumentError

KEY = b"cursor-key-for-tests-" + b"k" * 16
OLD_KEY = b"cursor-key-retired---" + b"o" * 16
POSITION = {"initiated_at": "2026-11-20T10:15:00+00:00", "txn_id": "txn_01JZ8Q4V9X2M3N4P5Q6R7S8T9V"}
QUERY = {"account_id": "acc_01JZ8Q4V9X2M3N4P5Q6R7S8T9V", "statuses": ["posted"]}
SUB = "staff-0042"
NOW = 1_800_000_000.0


class Clock:
    def __init__(self, now: float = NOW) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _cursors(*keys: bytes, clock: Clock | None = None) -> Cursors:
    return Cursors(keys or (KEY,), clock=clock or Clock())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_a_cursor_opens_to_the_position_it_was_issued_for() -> None:
    cursors = _cursors()

    cursor = cursors.issue(POSITION, query=QUERY, sub=SUB)

    assert cursors.open(cursor, query=QUERY, sub=SUB) == POSITION


def test_the_query_is_compared_in_canonical_form() -> None:
    cursors = _cursors()
    cursor = cursors.issue(POSITION, query=QUERY, sub=SUB)

    reordered = dict(reversed(QUERY.items()))

    assert cursors.open(cursor, query=reordered, sub=SUB) == POSITION


def test_a_cursor_for_another_query_is_refused() -> None:
    cursors = _cursors()
    cursor = cursors.issue(POSITION, query=QUERY, sub=SUB)

    with pytest.raises(InvalidArgumentError, match="another query"):
        cursors.open(cursor, query={**QUERY, "statuses": ["held"]}, sub=SUB)


def test_a_cursor_issued_to_someone_else_is_refused() -> None:
    cursors = _cursors()
    cursor = cursors.issue(POSITION, query=QUERY, sub=SUB)

    with pytest.raises(InvalidArgumentError, match="issued to someone else"):
        cursors.open(cursor, query=QUERY, sub="staff-0099")


def test_a_cursor_expires_after_fifteen_minutes() -> None:
    clock = Clock()
    cursors = _cursors(clock=clock)
    cursor = cursors.issue(POSITION, query=QUERY, sub=SUB)

    clock.now = NOW + 15 * 60
    assert cursors.open(cursor, query=QUERY, sub=SUB) == POSITION
    clock.now = NOW + 15 * 60 + 1
    with pytest.raises(InvalidArgumentError, match="expired"):
        cursors.open(cursor, query=QUERY, sub=SUB)


def test_an_edited_position_is_refused() -> None:
    cursors = _cursors()
    payload, signature = cursors.issue(POSITION, query=QUERY, sub=SUB).split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["k"]["txn_id"] = "txn_01JZ8Q4V9X2M3N4P5Q6R7S8T9W"

    forged = f"{_b64(json.dumps(claims).encode())}.{signature}"

    with pytest.raises(InvalidArgumentError, match="not valid"):
        cursors.open(forged, query=QUERY, sub=SUB)


def test_a_cursor_signed_under_the_previous_key_still_opens_during_rotation() -> None:
    cursor = _cursors(OLD_KEY).issue(POSITION, query=QUERY, sub=SUB)

    assert _cursors(KEY, OLD_KEY).open(cursor, query=QUERY, sub=SUB) == POSITION


def test_a_cursor_signed_under_an_unknown_key_is_refused() -> None:
    cursor = _cursors(OLD_KEY).issue(POSITION, query=QUERY, sub=SUB)

    with pytest.raises(InvalidArgumentError):
        _cursors(KEY).open(cursor, query=QUERY, sub=SUB)


def test_an_unknown_format_version_is_refused() -> None:
    cursors = _cursors()
    payload = {"v": 99, "k": POSITION, "q": "0" * 64, "sub": SUB, "exp": int(NOW) + 60}
    encoded = _b64(json.dumps(payload).encode())
    signature = _b64(hmac.new(KEY, encoded.encode(), hashlib.sha256).digest())

    with pytest.raises(InvalidArgumentError, match="not valid"):
        cursors.open(f"{encoded}.{signature}", query=QUERY, sub=SUB)


@pytest.mark.parametrize("key", [b"", b"short-key"])
def test_keys_must_be_long_enough(key: bytes) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        Cursors((key,))


def test_at_least_one_key_is_required() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Cursors(())


@given(garbage=st.text(max_size=300) | st.from_regex(r"\A[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\Z"))
def test_anything_else_is_an_invalid_argument(garbage: str) -> None:
    with pytest.raises(InvalidArgumentError):
        _cursors().open(garbage, query=QUERY, sub=SUB)
