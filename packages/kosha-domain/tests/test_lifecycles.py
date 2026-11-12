import re
from pathlib import Path

import pytest

from kosha_domain.lifecycles import (
    ACCOUNT,
    AML_ALERT,
    BENEFICIARY,
    CARD,
    DISPUTE,
    KYC_PROFILE,
    LIFECYCLES,
    TRANSACTION,
    TRANSACTION_REVIEW,
    AccountStatus,
    AnyLifecycle,
    IllegalTransitionError,
    TransactionStatus,
)

LLD = Path(__file__).parents[3] / "docs" / "architecture" / "lld" / "data-model.md"

# Status lists exactly as plan v0.2 §1a defines them.
PLAN_STATUSES = {
    "Transaction": (
        "initiated authorised processing pending success credit_delayed deemed_success on_hold "
        "under_review pending_settlement settled failed timed_out declined cancelled expired "
        "returned reversal_initiated reversed partially_reversed refunded chargeback_initiated"
    ),
    "Account": (
        "pending_activation active kyc_pending dormant inoperative debit_freeze credit_freeze "
        "total_freeze lien_marked on_hold pending_closure closed"
    ),
    "KYC profile": (
        "not_started pending_documents pending_vcip in_review on_hold escalated verified "
        "rejected re_kyc_due re_kyc_overdue expired"
    ),
    "Card": "inactive active temp_blocked pin_blocked blocked hotlisted expired replaced",
    "Dispute": (
        "raised acknowledged awaiting_customer_info under_investigation on_hold "
        "chargeback_raised pre_arbitration arbitration resolved_customer_favour "
        "resolved_merchant_favour auto_reversed withdrawn closed"
    ),
    "AML alert": (
        "open assigned in_review pending_info on_hold escalated closed_false_positive "
        "closed_no_action closed_str_filed"
    ),
    "Transaction review": "queued in_review on_hold cleared escalated_to_aml blocked",
    "Beneficiary": "pending_cooling active disabled deleted",
}


def lld_state_diagrams() -> dict[str, tuple[str, set[tuple[str, str]]]]:
    """Each '### <Entity>' section's Mermaid state diagram as (initial, edges)."""
    diagrams: dict[str, tuple[str, set[tuple[str, str]]]] = {}
    sections = re.split(r"^### ", LLD.read_text(encoding="utf-8"), flags=re.MULTILINE)
    for section in sections[1:]:
        title, _, body = section.partition("\n")
        if "stateDiagram-v2" not in body:
            continue
        edges = set(re.findall(r"^\s+(\S+) --> (\S+)\s*$", body, flags=re.MULTILINE))
        initial = next(dst for src, dst in edges if src == "[*]")
        diagrams[title.strip()] = (initial, {e for e in edges if "[*]" not in e})
    return diagrams


def test_every_planned_entity_has_exactly_one_lifecycle() -> None:
    assert sorted(lc.name for lc in LIFECYCLES) == sorted(PLAN_STATUSES)


@pytest.mark.parametrize("lifecycle", LIFECYCLES, ids=lambda lc: lc.name)
def test_statuses_match_the_plan(lifecycle: AnyLifecycle) -> None:
    assert {s.value for s in lifecycle.statuses} == set(PLAN_STATUSES[lifecycle.name].split())


@pytest.mark.parametrize("lifecycle", LIFECYCLES, ids=lambda lc: lc.name)
def test_transitions_match_the_lld_state_diagram(lifecycle: AnyLifecycle) -> None:
    initial, edges = lld_state_diagrams()[lifecycle.name]

    assert lifecycle.initial.value == initial
    assert {(a.value, b.value) for a, b in lifecycle.transitions} == edges


@pytest.mark.parametrize("lifecycle", LIFECYCLES, ids=lambda lc: lc.name)
def test_every_status_is_reachable_from_the_initial_status(lifecycle: AnyLifecycle) -> None:
    for status in lifecycle.statuses:
        assert lifecycle.path_to(status)[0] == lifecycle.initial


@pytest.mark.parametrize(
    ("lifecycle", "src", "dst"),
    [
        (TRANSACTION, "pending", "credit_delayed"),
        (ACCOUNT, "dormant", "inoperative"),
        (KYC_PROFILE, "re_kyc_due", "re_kyc_overdue"),
        (DISPUTE, "raised", "auto_reversed"),
        (AML_ALERT, "escalated", "closed_str_filed"),
        (CARD, "hotlisted", "replaced"),
        (TRANSACTION_REVIEW, "in_review", "escalated_to_aml"),
        (BENEFICIARY, "pending_cooling", "active"),
    ],
)
def test_legal_transitions_are_allowed(lifecycle: AnyLifecycle, src: str, dst: str) -> None:
    status = lifecycle.status_type
    assert lifecycle.can_transition(status(src), status(dst))
    lifecycle.ensure_transition(status(src), status(dst))


@pytest.mark.parametrize(
    ("lifecycle", "src", "dst"),
    [
        (TRANSACTION, "failed", "success"),  # a failed payment never succeeds later
        (TRANSACTION, "settled", "settled"),  # no self-transitions
        (ACCOUNT, "active", "inoperative"),  # RBI: only a dormant account becomes inoperative
        (ACCOUNT, "closed", "active"),
        (AML_ALERT, "in_review", "closed_str_filed"),  # an STR needs escalation first
        (CARD, "hotlisted", "active"),  # lost or stolen cards are never reactivated
        (BENEFICIARY, "deleted", "active"),
    ],
)
def test_illegal_transitions_are_rejected(lifecycle: AnyLifecycle, src: str, dst: str) -> None:
    status = lifecycle.status_type
    assert not lifecycle.can_transition(status(src), status(dst))
    with pytest.raises(IllegalTransitionError, match=f"{lifecycle.name}.*{src}.*{dst}"):
        lifecycle.ensure_transition(status(src), status(dst))


def test_path_to_is_the_shortest_route_from_the_initial_status() -> None:
    assert TRANSACTION.path_to(TransactionStatus.SETTLED) == [
        TransactionStatus.INITIATED,
        TransactionStatus.AUTHORISED,
        TransactionStatus.PROCESSING,
        TransactionStatus.SUCCESS,
        TransactionStatus.PENDING_SETTLEMENT,
        TransactionStatus.SETTLED,
    ]


def test_path_to_the_initial_status_is_just_that_status() -> None:
    assert ACCOUNT.path_to(AccountStatus.PENDING_ACTIVATION) == [AccountStatus.PENDING_ACTIVATION]


def test_next_statuses_lists_every_permitted_destination() -> None:
    assert ACCOUNT.next_statuses(AccountStatus.DORMANT) == {
        AccountStatus.INOPERATIVE,
        AccountStatus.ACTIVE,
    }
