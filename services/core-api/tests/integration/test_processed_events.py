"""Consumers record each event they apply, so a redelivered event takes effect once."""

import psycopg
import pytest
from psycopg import errors

from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.integration

_RECORD = """
    INSERT INTO ops.processed_events (consumer, event_id)
    VALUES (%s, %s)
    ON CONFLICT DO NOTHING
    RETURNING event_id
"""


def test_the_first_delivery_is_recorded_and_a_redelivery_is_not(db: psycopg.Connection) -> None:
    db.execute("SET LOCAL ROLE kosha_app")
    event_id = new_id(IdPrefix.OUTBOX_EVENT)

    first = db.execute(_RECORD, ["events-worker", event_id]).fetchone()
    again = db.execute(_RECORD, ["events-worker", event_id]).fetchone()

    assert (first, again) == ((event_id,), None)


def test_each_consumer_dedupes_on_its_own(db: psycopg.Connection) -> None:
    db.execute("SET LOCAL ROLE kosha_app")
    event_id = new_id(IdPrefix.OUTBOX_EVENT)

    for consumer in ("events-worker", "review-queue"):
        assert db.execute(_RECORD, [consumer, event_id]).fetchone() == (event_id,)


def test_only_outbox_event_ids_are_accepted(db: psycopg.Connection) -> None:
    with pytest.raises(errors.CheckViolation):
        db.execute(_RECORD, ["events-worker", new_id(IdPrefix.DISPUTE)])


def test_the_application_role_may_purge_old_records(db: psycopg.Connection) -> None:
    row = db.execute(
        "SELECT has_table_privilege('kosha_app', 'ops.processed_events', 'DELETE')"
    ).fetchone()

    assert row == (True,)
