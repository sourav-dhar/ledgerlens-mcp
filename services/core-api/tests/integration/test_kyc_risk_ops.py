"""KYC, risk and operations tables: PII tripwires, consistency and append-only audit."""

from typing import LiteralString

import db_rows as rows
import psycopg
import pytest
from psycopg import errors

from kosha_domain.ids import IdPrefix, new_id

pytestmark = pytest.mark.integration


# --- KYC: full identity numbers never reach the database


def test_a_full_aadhaar_number_cannot_be_stored_as_its_vault_token(db: psycopg.Connection) -> None:
    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.kyc_profile(db, rows.customer(db), aadhaar_ref_token="234123412346")  # noqa: S106 — synthetic raw identifier


def test_a_plain_pan_cannot_be_stored_as_its_encrypted_token(db: psycopg.Connection) -> None:
    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.kyc_profile(db, rows.customer(db), pan_token="AAAPL1234C")  # noqa: S106 — synthetic raw identifier


@pytest.mark.parametrize(
    ("column", "value"),
    [("aadhaar_last4", "48210"), ("pan_last4", "2345"), ("ckyc_number", "1234")],
)
def test_partial_identifiers_have_their_documented_shape(
    db: psycopg.Connection, column: str, value: str
) -> None:
    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.kyc_profile(db, rows.customer(db), **{column: value})


def test_a_kyc_document_belongs_to_its_profiles_customer(db: psycopg.Connection) -> None:
    kyc_id = rows.kyc_profile(db, rows.customer(db))
    document = {
        "kyc_id": kyc_id,
        "doc_type": "pan_card",
        "s3_key": "kyc/documents/pan.png",
        "sha256": "a" * 64,
        "status": "accepted",
        "uploaded_at": rows.NOW,
    }

    with pytest.raises(errors.ForeignKeyViolation), db.transaction():
        rows.insert(
            db,
            "kyc.kyc_documents",
            document
            | {"document_id": new_id(IdPrefix.KYC_DOCUMENT), "customer_id": rows.customer(db)},
        )


# --- Risk


def test_an_alert_carries_its_rules_typology(db: psycopg.Connection) -> None:
    rule_id = rows.aml_rule(db, typology="structuring")

    with pytest.raises(errors.ForeignKeyViolation), db.transaction():
        rows.aml_alert(db, rows.customer(db), rule_id, typology="velocity")


def test_an_alert_closed_with_an_str_names_the_filing(db: psycopg.Connection) -> None:
    customer_id, rule_id = rows.customer(db), rows.aml_rule(db)
    rows.aml_alert(db, customer_id, rule_id, status="closed_str_filed", str_reference="STR/1")

    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.aml_alert(db, customer_id, rule_id, status="closed_str_filed")


def test_rule_parameters_are_a_json_object(db: psycopg.Connection) -> None:
    with pytest.raises(errors.CheckViolation), db.transaction():
        rows.aml_rule(db, params="[1, 2]")


# --- Operations


def test_an_idempotency_key_is_unique_within_its_scope(db: psycopg.Connection) -> None:
    record = {
        "key": "4f1c-retry",
        "request_hash": "b" * 64,
        "status": "in_progress",
        "expires_at": rows.NOW,
    }
    rows.insert(db, "ops.idempotency_keys", record | {"scope": "raise_dispute"})
    rows.insert(db, "ops.idempotency_keys", record | {"scope": "flag_transaction"})

    with pytest.raises(errors.UniqueViolation), db.transaction():
        rows.insert(db, "ops.idempotency_keys", record | {"scope": "raise_dispute"})


def test_the_application_role_appends_audit_records(db: psycopg.Connection) -> None:
    with db.transaction():
        db.execute("SET LOCAL ROLE kosha_app")
        rows.audit_record(db)


@pytest.mark.parametrize(
    "statement",
    ["UPDATE ops.audit_log SET outcome = 'error'", "DELETE FROM ops.audit_log"],
)
def test_the_application_role_cannot_alter_audit_records(
    db: psycopg.Connection, statement: LiteralString
) -> None:
    db.execute("SET LOCAL ROLE kosha_app")

    with pytest.raises(errors.InsufficientPrivilege), db.transaction():
        db.execute(statement)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ops.audit_log SET outcome = 'error'",
        "DELETE FROM ops.audit_log",
        "TRUNCATE ops.audit_log",
    ],
)
def test_not_even_the_owner_can_alter_audit_records(
    db: psycopg.Connection, statement: LiteralString
) -> None:
    rows.audit_record(db)

    with pytest.raises(errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute(statement)


def test_queue_indexes_from_the_design_exist(db: psycopg.Connection) -> None:
    rows_ = db.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname IN ('risk', 'ops')"
    ).fetchall()

    assert {"aml_alerts_queue_idx", "outbox_unpublished_idx"} <= {name for (name,) in rows_}
