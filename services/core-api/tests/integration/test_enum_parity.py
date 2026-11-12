"""Postgres enum types match their kosha-domain enums label for label, in order.

Migrations freeze enum labels as literals so that old revisions never change when the domain
moves on. This test is what keeps the two in step: adding a value to a domain enum without a
migration (or the reverse) fails here.
"""

from enum import StrEnum

import psycopg
import pytest

from kosha_domain import lifecycles as lc
from kosha_domain import vocabulary as v

pytestmark = pytest.mark.integration

DOMAIN_ENUMS: dict[str, type[StrEnum]] = {
    "kosha.actor": v.Actor,
    "kosha.risk_category": v.RiskCategory,
    "core.gender": v.Gender,
    "core.persona": v.Persona,
    "core.segment": v.Segment,
    "core.income_band": v.IncomeBand,
    "core.residential_status": v.ResidentialStatus,
    "core.onboarding_channel": v.OnboardingChannel,
    "core.customer_status": v.CustomerStatus,
    "core.address_type": v.AddressType,
    "core.product_code": v.ProductCode,
    "core.mode_of_operation": v.ModeOfOperation,
    "core.account_status": lc.AccountStatus,
    "core.card_network": v.CardNetwork,
    "core.card_type": v.CardType,
    "core.card_status": lc.CardStatus,
    "core.vpa_status": v.VpaStatus,
    "core.beneficiary_status": lc.BeneficiaryStatus,
    "core.direction": v.Direction,
    "core.rail": v.Rail,
    "core.transaction_type": v.TransactionType,
    "core.channel": v.Channel,
    "core.transaction_status": lc.TransactionStatus,
    "ledger.gl_account": v.GlAccount,
    "kyc.kyc_type": v.KycType,
    "kyc.kyc_status": lc.KycStatus,
    "kyc.pan_status": v.PanStatus,
    "kyc.ovd_type": v.OvdType,
    "kyc.document_type": v.KycDocumentType,
    "kyc.document_status": v.KycDocumentStatus,
    "risk.typology": v.Typology,
    "risk.severity": v.Severity,
    "risk.list_source": v.ListSource,
    "risk.screening_decision": v.ScreeningDecision,
    "risk.aml_alert_status": lc.AmlAlertStatus,
    "ops.dispute_reason": v.DisputeReason,
    "ops.dispute_status": lc.DisputeStatus,
    "ops.review_priority": v.ReviewPriority,
    "ops.transaction_review_status": lc.TransactionReviewStatus,
    "ops.idempotency_status": v.IdempotencyStatus,
    "ops.audit_outcome": v.AuditOutcome,
}

_DB_ENUMS = """
    SELECT n.nspname || '.' || t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder)
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    JOIN pg_enum e ON e.enumtypid = t.oid
    WHERE n.nspname = ANY(%s)
    GROUP BY 1
"""


@pytest.fixture
def db_enums(db: psycopg.Connection) -> dict[str, list[str]]:
    schemas = ["kosha", "core", "ledger", "kyc", "risk", "ops", "kb"]
    return dict(db.execute(_DB_ENUMS, [schemas]).fetchall())


def test_every_database_enum_has_a_domain_enum(db_enums: dict[str, list[str]]) -> None:
    assert sorted(db_enums) == sorted(DOMAIN_ENUMS)


@pytest.mark.parametrize("type_name", sorted(DOMAIN_ENUMS))
def test_labels_match_the_domain_in_order(db_enums: dict[str, list[str]], type_name: str) -> None:
    assert db_enums[type_name] == [member.value for member in DOMAIN_ENUMS[type_name]]
