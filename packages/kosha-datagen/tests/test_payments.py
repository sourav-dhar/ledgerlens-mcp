"""Transactions move through legal lifecycles, and the ledger they post to always balances."""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from kosha_datagen import Batch
from kosha_domain.ids import IdPrefix, is_valid_id
from kosha_domain.lifecycles import TRANSACTION, AccountStatus, TransactionStatus
from kosha_domain.validators import is_valid_rrn, is_valid_utr
from kosha_domain.vocabulary import GlAccount, ProductCode, Rail, TransactionType

T = TransactionStatus
NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
WINDOW_START = datetime(2025, 6, 1, tzinfo=UTC)
SETTLED_OK = {T.SUCCESS, T.PENDING_SETTLEMENT, T.SETTLED}
NO_MONEY_MOVED = {T.FAILED, T.DECLINED, T.CANCELLED, T.EXPIRED, T.ON_HOLD, T.UNDER_REVIEW}
IN_FLIGHT = {T.CREDIT_DELAYED, T.DEEMED_SUCCESS, T.ON_HOLD, T.UNDER_REVIEW, T.RETURNED, T.PENDING}
SYSTEM_TYPES = {TransactionType.INTEREST_CREDIT, TransactionType.CHARGES}


def test_customers_transact_about_three_hundred_times_over_the_window(dataset: Batch) -> None:
    per_customer = len(dataset.transactions) / len(dataset.customers)

    assert 200 <= per_customer <= 400
    assert all(is_valid_id(t.txn_id, IdPrefix.TRANSACTION) for t in dataset.transactions)
    assert all(WINDOW_START <= t.initiated_at <= NOW for t in dataset.transactions)


def test_every_history_is_a_legal_path_ending_in_the_current_status(dataset: Batch) -> None:
    history = defaultdict[str, list[tuple[T | None, T, datetime]]](list)
    for h in dataset.transaction_status_history:
        history[h.txn_id].append((h.from_status, h.to_status, h.occurred_at))

    for txn in dataset.transactions:
        steps = sorted(history[txn.txn_id], key=lambda s: s[2])
        assert steps[0][:2] == (None, T.INITIATED), txn
        assert steps[0][2] == txn.initiated_at
        for previous, step in pairwise(steps):
            assert step[0] is previous[1]
            assert TRANSACTION.can_transition(previous[1], step[1]), steps
        assert steps[-1][1] is txn.status


def test_most_transactions_succeed_and_a_few_fail(dataset: Batch) -> None:
    statuses = Counter(t.status for t in dataset.transactions)
    total = statuses.total()

    assert sum(statuses[s] for s in SETTLED_OK) / total >= 0.93
    assert 0.004 <= (statuses[T.FAILED] + statuses[T.DECLINED]) / total <= 0.03
    assert statuses[T.REVERSED] > 0
    assert statuses[T.REFUNDED] > 0


def test_in_flight_states_are_recent(dataset: Batch) -> None:
    for t in dataset.transactions:
        if t.status in IN_FLIGHT:
            assert t.initiated_at >= NOW - timedelta(days=7), t


def test_every_entry_balances_across_at_least_two_postings(dataset: Batch) -> None:
    by_entry = defaultdict[str, list[int]](list)
    for p in dataset.postings:
        by_entry[p.entry_id].append(p.amount_paise)
        assert (p.gl_account is GlAccount.CUSTOMER_DEPOSITS) == (p.account_id is not None)

    assert set(by_entry) == {e.entry_id for e in dataset.journal_entries}
    for amounts in by_entry.values():
        assert len(amounts) >= 2
        assert sum(amounts) == 0
        assert 0 not in amounts


def test_money_moves_exactly_when_the_status_says_it_did(dataset: Batch) -> None:
    posted = Counter(e.txn_id for e in dataset.journal_entries if e.txn_id)

    for t in dataset.transactions:
        expected = 0 if t.status in NO_MONEY_MOVED else 1
        assert posted[t.txn_id] == expected, t
        assert (t.balance_after_paise is None) == (expected == 0), t


def test_cached_balances_equal_the_sum_of_postings(dataset: Batch) -> None:
    posted = Counter[str]()
    for p in dataset.postings:
        if p.account_id:
            posted[p.account_id] += p.amount_paise

    for a in dataset.accounts:
        assert a.ledger_balance_paise == posted[a.account_id], a
        assert a.ledger_balance_paise >= 0, a
        assert a.hold_amount_paise >= 0, a


def test_no_account_is_ever_overdrawn(dataset: Batch) -> None:
    posted_at = {e.entry_id: e.posted_at for e in dataset.journal_entries}
    movements = defaultdict[str, list[tuple[datetime, int]]](list)
    for p in dataset.postings:
        if p.account_id:
            movements[p.account_id].append((posted_at[p.entry_id], p.amount_paise))

    for account_id, moves in movements.items():
        balance = 0
        for _, amount in sorted(moves, key=lambda m: (m[0], -m[1])):
            balance += amount
            assert balance >= 0, account_id


def test_balance_after_is_a_running_balance(dataset: Batch) -> None:
    # Deposits also grow through bookings recorded on the funding Account's Transaction, so
    # only Accounts whose every movement is their own Transaction are checked.
    own_movements = {
        a.account_id: a.ledger_balance_paise
        for a in dataset.accounts
        if a.product_code not in (ProductCode.FIXED_DEPOSIT, ProductCode.RECURRING_DEPOSIT)
    }
    last: dict[str, int] = {}
    for t in sorted(dataset.transactions, key=lambda t: t.posted_at or NOW):
        if t.balance_after_paise is not None:
            last[t.account_id] = t.balance_after_paise

    assert last
    for account_id, balance in own_movements.items():
        if account_id in last:
            assert last[account_id] == balance, account_id


def test_accounts_older_than_the_ledger_bring_their_balance_forward(dataset: Batch) -> None:
    opening = {e.entry_id for e in dataset.journal_entries if e.txn_id is None}
    brought_forward = {
        p.account_id for p in dataset.postings if p.entry_id in opening and p.account_id
    }
    contra = [p for p in dataset.postings if p.gl_account is GlAccount.OPENING_BALANCES]

    old = {a.account_id for a in dataset.accounts if a.opened_at < WINDOW_START}
    assert old
    assert brought_forward <= old
    assert len(brought_forward) >= 0.8 * len(old)
    assert all(p.amount_paise < 0 for p in contra)


def test_returned_money_comes_back_as_its_own_credit_transaction(dataset: Batch) -> None:
    by_id = {t.txn_id: t for t in dataset.transactions}
    returned = {T.REVERSED, T.PARTIALLY_REVERSED, T.REFUNDED}
    compensations = [
        t
        for t in dataset.transactions
        if t.txn_type in (TransactionType.REVERSAL, TransactionType.REFUND)
    ]

    assert len(compensations) == sum(1 for t in dataset.transactions if t.status in returned)
    for c in compensations:
        assert c.remarks is not None
        original = by_id[c.remarks.rsplit(" ", 1)[-1]]
        assert original.status in returned
        assert (original.account_id, original.direction) == (c.account_id, "debit")
        assert c.amount_paise <= original.amount_paise
        assert c.initiated_at >= original.initiated_at


def test_references_have_the_shape_their_rail_issues(dataset: Batch) -> None:
    for t in dataset.transactions:
        if t.rrn is not None:
            assert is_valid_rrn(t.rrn), t
        if t.rail in (Rail.NEFT, Rail.RTGS, Rail.IMPS):
            assert t.utr is not None
            assert is_valid_utr(t.utr, t.rail), t
        if t.rail is Rail.UPI:
            assert t.rrn is not None
            assert t.npci_txn_id is not None


def test_dormant_and_inoperative_accounts_see_only_bank_initiated_activity(
    dataset: Batch,
) -> None:
    status = {a.account_id: a.status for a in dataset.accounts}
    for t in dataset.transactions:
        if t.txn_type in SYSTEM_TYPES:
            continue
        if status[t.account_id] is AccountStatus.INOPERATIVE:
            raise AssertionError(t)
        if status[t.account_id] is AccountStatus.DORMANT:
            assert t.initiated_at < NOW - timedelta(days=365), t


def test_closed_accounts_end_empty_with_nothing_after_closure(dataset: Batch) -> None:
    closed = {a.account_id: a for a in dataset.accounts if a.status is AccountStatus.CLOSED}

    assert closed
    for a in closed.values():
        assert a.ledger_balance_paise == 0
    for t in dataset.transactions:
        account = closed.get(t.account_id)
        if account is not None:
            assert account.closed_at is not None
            assert t.initiated_at <= account.closed_at


def test_held_transactions_are_held_on_their_account(dataset: Batch) -> None:
    held = Counter[str]()
    for t in dataset.transactions:
        if t.status in (T.ON_HOLD, T.UNDER_REVIEW):
            held[t.account_id] += t.amount_paise

    holds = {a.account_id: a.hold_amount_paise for a in dataset.accounts}
    for account_id, amount in held.items():
        assert holds[account_id] >= amount
