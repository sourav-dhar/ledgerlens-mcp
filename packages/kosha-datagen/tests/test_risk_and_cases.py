"""AML alerts come from running the rules over Transactions; disputes and reviews from the tail."""

from collections import Counter
from datetime import UTC, date, datetime, timedelta

import pytest

from kosha_datagen import Batch, GenerationConfig, generate
from kosha_domain.ids import IdPrefix, is_valid_id
from kosha_domain.lifecycles import AmlAlertStatus, DisputeStatus, TransactionStatus
from kosha_domain.vocabulary import Typology

NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
A = AmlAlertStatus
CLOSED = {A.CLOSED_FALSE_POSITIVE, A.CLOSED_NO_ACTION, A.CLOSED_STR_FILED}


@pytest.fixture(scope="module")
def planted() -> Batch:
    """Enough Customers that every typology is planted at least once."""
    return Batch.merge(generate(GenerationConfig(as_of=date(2026, 11, 12), seed=5, scale=0.075)))


def test_there_is_one_enabled_rule_per_typology(dataset: Batch) -> None:
    rules = dataset.aml_rules

    assert sorted(r.typology for r in rules) == sorted(Typology)
    assert all(is_valid_id(r.rule_id, IdPrefix.AML_RULE) and r.enabled for r in rules)
    assert all(r.params for r in rules)


def test_every_planted_typology_fires_an_alert(planted: Batch) -> None:
    fired = {a.typology for a in planted.aml_alerts}

    assert fired == set(Typology)


def test_alerts_cite_real_transactions_of_their_customer(planted: Batch) -> None:
    owner = {t.txn_id: t.customer_id for t in planted.transactions}
    rule_typology = {r.rule_id: r.typology for r in planted.aml_rules}

    for alert in planted.aml_alerts:
        assert alert.triggering_txn_ids
        assert {owner[t] for t in alert.triggering_txn_ids} == {alert.customer_id}
        assert rule_typology[alert.rule_id] is alert.typology


def test_alert_volume_is_a_few_percent_of_customers(planted: Batch) -> None:
    ratio = len(planted.aml_alerts) / len(planted.customers)

    assert 0.03 <= ratio <= 0.15


def test_alerts_age_into_their_dispositions(planted: Batch) -> None:
    for alert in planted.aml_alerts:
        assert alert.created_at <= NOW
        assert alert.sla_due_at > alert.created_at
        assert (alert.status in CLOSED) == (alert.closed_at is not None), alert
        assert (alert.status is A.CLOSED_STR_FILED) == (alert.str_reference is not None)
        assert (alert.status is A.OPEN) == (alert.assigned_to is None), alert
        if alert.status is A.OPEN:
            assert alert.created_at >= NOW - timedelta(days=14)


def test_most_closed_alerts_are_false_positives_but_some_end_in_strs(planted: Batch) -> None:
    closed = Counter(a.status for a in planted.aml_alerts if a.status in CLOSED)

    assert closed[A.CLOSED_STR_FILED] >= 1
    assert closed[A.CLOSED_FALSE_POSITIVE] >= closed[A.CLOSED_STR_FILED]


def test_disputes_concern_the_customers_own_transactions(planted: Batch) -> None:
    txns = {t.txn_id: t for t in planted.transactions}
    ratio = len(planted.disputes) / len(planted.customers)

    assert 0.05 <= ratio <= 0.25
    for d in planted.disputes:
        txn = txns[d.txn_id]
        assert (txn.customer_id, txn.initiated_at) == (d.customer_id, d.txn_initiated_at)
        assert 0 < d.amount_paise <= txn.amount_paise
        assert txn.initiated_at <= d.created_at <= NOW
        assert d.tat_due_at > txn.initiated_at


def test_a_chargeback_always_has_a_dispute_behind_it(planted: Batch) -> None:
    disputed = {d.txn_id: d.status for d in planted.disputes}
    chargebacks = [
        t for t in planted.transactions if t.status is TransactionStatus.CHARGEBACK_INITIATED
    ]

    assert chargebacks
    for txn in chargebacks:
        assert disputed[txn.txn_id] in {
            DisputeStatus.CHARGEBACK_RAISED,
            DisputeStatus.PRE_ARBITRATION,
            DisputeStatus.ARBITRATION,
        }


def test_late_reversals_owe_one_hundred_rupees_a_day(planted: Batch) -> None:
    compensated = [d for d in planted.disputes if d.compensation_paise]

    assert compensated
    assert all(d.compensation_paise % 10_000 == 0 for d in compensated)


def test_every_flagged_transaction_is_queued_for_review(planted: Batch) -> None:
    reviewed = Counter(r.txn_id for r in planted.transaction_reviews)
    flagged = {t.txn_id for t in planted.transactions if t.is_flagged}

    assert flagged
    assert set(reviewed) == flagged
    assert set(reviewed.values()) == {1}
