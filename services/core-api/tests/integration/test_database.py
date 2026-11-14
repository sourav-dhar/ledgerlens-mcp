"""A unit of work is one transaction, run as the application role with the caller's context."""

import anyio
import db_rows as rows
import psycopg
import pytest
from psycopg import errors
from pydantic import SecretStr

from core_api.db import Caller, Database
from core_api.errors import (
    ConflictError,
    DeadlineExceededError,
    UnavailableError,
    from_database_error,
)
from core_api.migrations import head
from core_api.settings import Settings
from kosha_domain.vocabulary import Classification

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

STAFF = Caller(actor="staff-0042", kb_ceiling=Classification.INTERNAL)


async def test_work_runs_as_the_application_role_with_the_callers_context(
    database: Database,
) -> None:
    async with database.unit_of_work(STAFF) as conn:
        row = await (
            await conn.execute(
                "SELECT current_user AS role, current_setting('kosha.actor') AS actor,"
                " current_setting('kosha.kb_ceiling') AS ceiling"
            )
        ).fetchone()

    assert row == {"role": "kosha_app", "actor": "staff-0042", "ceiling": "internal"}


async def test_the_context_ends_with_the_transaction(api_settings: Settings) -> None:
    database = Database.from_settings(api_settings.model_copy(update={"db_pool_max_size": 1}))
    await database.open()
    try:
        async with database.unit_of_work(STAFF):
            pass
        async with database.unit_of_work(Caller(actor="analyst-7")) as conn:
            row = await (
                await conn.execute(
                    "SELECT current_setting('kosha.actor') AS actor,"
                    " current_setting('kosha.kb_ceiling', true) AS ceiling"
                )
            ).fetchone()
    finally:
        await database.close()

    assert row == {"actor": "analyst-7", "ceiling": ""}


async def test_a_read_only_unit_refuses_to_write(
    database: Database, committed: psycopg.Connection
) -> None:
    customer_id = rows.customer(committed)

    with pytest.raises(errors.ReadOnlySqlTransaction):
        async with database.unit_of_work(STAFF, read_only=True) as conn:
            await conn.execute(
                "UPDATE core.customers SET occupation = 'Teacher' WHERE customer_id = %s",
                [customer_id],
            )


async def test_work_commits_on_success_and_rolls_back_on_error(
    database: Database, committed: psycopg.Connection
) -> None:
    kept, undone = rows.customer(committed), rows.customer(committed)
    update = "UPDATE core.customers SET occupation = 'Teacher' WHERE customer_id = %s"

    async def update_then_fail() -> None:
        async with database.unit_of_work(STAFF) as conn:
            await conn.execute(update, [undone])
            raise RuntimeError

    async with database.unit_of_work(STAFF) as conn:
        await conn.execute(update, [kept])
    with pytest.raises(RuntimeError):
        await update_then_fail()

    occupations = committed.execute(
        "SELECT customer_id, occupation FROM core.customers WHERE customer_id = ANY(%s)",
        [[kept, undone]],
    ).fetchall()
    assert dict(occupations) == {kept: "Teacher", undone: None}


async def test_a_slow_statement_exceeds_its_deadline(api_settings: Settings) -> None:
    settings = api_settings.model_copy(update={"db_statement_timeout_ms": 50})
    database = Database.from_settings(settings)
    await database.open()
    try:
        with pytest.raises(errors.QueryCanceled) as caught:
            async with database.unit_of_work(STAFF, read_only=True) as conn:
                await conn.execute("SELECT pg_sleep(1)")
    finally:
        await database.close()

    assert isinstance(from_database_error(caught.value), DeadlineExceededError)


async def test_an_exhausted_pool_is_unavailable(api_settings: Settings) -> None:
    settings = api_settings.model_copy(update={"db_pool_max_size": 1, "db_pool_timeout_s": 0.2})
    database = Database.from_settings(settings)
    await database.open()
    try:
        async with database.unit_of_work(STAFF):
            with pytest.raises(Exception) as caught:  # noqa: PT011 — the type is the assertion
                async with database.unit_of_work(STAFF):
                    pass
    finally:
        await database.close()

    assert isinstance(from_database_error(caught.value), UnavailableError)


async def test_an_illegal_status_change_is_a_conflict(
    database: Database, committed: psycopg.Connection
) -> None:
    account_id = rows.account(committed, rows.customer(committed), status="closed")

    with pytest.raises(errors.CheckViolation) as caught:
        async with database.unit_of_work(STAFF) as conn:
            await conn.execute(
                "UPDATE core.accounts SET status = 'active' WHERE account_id = %s", [account_id]
            )

    conflict = from_database_error(caught.value)
    assert isinstance(conflict, ConflictError)
    assert "cannot move from 'closed' to 'active'" in conflict.message


async def test_changing_append_only_history_is_a_conflict(
    database: Database, committed: psycopg.Connection
) -> None:
    audit_id = rows.audit_record(committed)

    with pytest.raises(errors.InsufficientPrivilege):
        async with database.unit_of_work(STAFF) as conn:
            await conn.execute("DELETE FROM ops.audit_log WHERE audit_id = %s", [audit_id])
    with pytest.raises(errors.RestrictViolation) as caught:
        committed.execute("DELETE FROM ops.audit_log WHERE audit_id = %s", [audit_id])

    assert isinstance(from_database_error(caught.value), ConflictError)


async def test_the_schema_revision_is_read_from_the_database(database: Database) -> None:
    assert await database.schema_revision() == head()


async def test_an_unreachable_database_has_no_revision() -> None:
    unreachable = SecretStr("postgresql://nobody@127.0.0.1:9/none")
    database = Database.from_settings(Settings(database_url=unreachable, db_pool_timeout_s=0.2))
    await database.open()
    try:
        with anyio.fail_after(5):
            assert await database.schema_revision() is None
    finally:
        await database.close()
