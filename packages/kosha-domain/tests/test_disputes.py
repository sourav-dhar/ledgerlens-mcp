"""Dispute rules follow RBI's TAT harmonisation circular."""

from datetime import timedelta

import pytest

from kosha_domain.disputes import (
    COMPENSATION_PER_DAY_PAISE,
    OPEN_DISPUTE_STATUSES,
    is_disputable,
    turnaround,
)
from kosha_domain.lifecycles import DISPUTE, DisputeStatus, TransactionStatus
from kosha_domain.vocabulary import Direction, Rail

T = TransactionStatus
D = DisputeStatus


@pytest.mark.parametrize("rail", [Rail.ATM, Rail.CARD_POS, Rail.CARD_ECOM])
def test_card_and_atm_failures_turn_around_in_five_days(rail: Rail) -> None:
    assert turnaround(rail) == timedelta(days=5)


@pytest.mark.parametrize("rail", [Rail.UPI, Rail.IMPS, Rail.NEFT, Rail.RTGS, Rail.NACH])
def test_account_to_account_failures_turn_around_in_one_day(rail: Rail) -> None:
    assert turnaround(rail) == timedelta(days=1)


def test_late_reversals_owe_one_hundred_rupees_a_day() -> None:
    assert COMPENSATION_PER_DAY_PAISE == 10_000


@pytest.mark.parametrize(
    "status",
    [T.SUCCESS, T.SETTLED, T.FAILED, T.TIMED_OUT, T.CREDIT_DELAYED, T.DEEMED_SUCCESS, T.REVERSED],
)
def test_a_debit_that_moved_money_can_be_disputed(status: TransactionStatus) -> None:
    assert is_disputable(Direction.DEBIT, status)


@pytest.mark.parametrize(
    "status",
    [T.INITIATED, T.AUTHORISED, T.PROCESSING, T.PENDING, T.DECLINED, T.CANCELLED, T.EXPIRED],
)
def test_a_debit_still_in_flight_or_that_never_moved_money_cannot(
    status: TransactionStatus,
) -> None:
    assert not is_disputable(Direction.DEBIT, status)


def test_a_credit_cannot_be_disputed() -> None:
    assert not is_disputable(Direction.CREDIT, T.SUCCESS)


def test_a_dispute_is_open_until_it_is_decided() -> None:
    decided = {
        D.RESOLVED_CUSTOMER_FAVOUR,
        D.RESOLVED_MERCHANT_FAVOUR,
        D.AUTO_REVERSED,
        D.WITHDRAWN,
        D.CLOSED,
    }

    assert set(DisputeStatus) - OPEN_DISPUTE_STATUSES == decided


def test_every_decided_dispute_can_only_close() -> None:
    for status in set(DisputeStatus) - OPEN_DISPUTE_STATUSES - {D.CLOSED}:
        assert DISPUTE.next_statuses(status) == {D.CLOSED}, status
