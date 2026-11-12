"""Accounts, cards, VPAs and Beneficiaries, and the KYC that let each Customer hold them."""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from kosha_datagen import Batch
from kosha_domain.ids import IdPrefix, is_valid_id
from kosha_domain.lifecycles import (
    KYC_PROFILE,
    AccountStatus,
    BeneficiaryStatus,
    CardStatus,
    KycStatus,
)
from kosha_domain.validators import is_valid_ifsc, is_valid_vpa
from kosha_domain.vocabulary import CustomerStatus, Persona, ProductCode, RiskCategory

NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)


def test_accounts_number_about_one_and_a_half_per_customer(dataset: Batch) -> None:
    ratio = len(dataset.accounts) / len(dataset.customers)

    assert 1.2 <= ratio <= 1.8
    assert all(is_valid_id(a.account_id, IdPrefix.ACCOUNT) for a in dataset.accounts)
    assert all(is_valid_ifsc(a.ifsc) for a in dataset.accounts)
    assert len({a.account_number for a in dataset.accounts}) == len(dataset.accounts)


def test_every_customer_has_one_operative_account_of_their_persona(dataset: Batch) -> None:
    by_customer = defaultdict[str, list[ProductCode]](list)
    for a in dataset.accounts:
        by_customer[a.customer_id].append(a.product_code)

    for c in dataset.customers:
        products = by_customer[c.customer_id]
        transactional = [p for p in products if p not in _DEPOSITS]
        assert len(transactional) >= 1, c
        if c.persona is Persona.SME_OWNER:
            assert ProductCode.CURRENT in products


def test_account_status_follows_the_customers_standing(dataset: Batch) -> None:
    status = {c.customer_id: c.status for c in dataset.customers}
    expected = {
        CustomerStatus.PROSPECT: {AccountStatus.PENDING_ACTIVATION, AccountStatus.KYC_PENDING},
        CustomerStatus.CLOSED: {AccountStatus.CLOSED},
        CustomerStatus.FROZEN: {AccountStatus.TOTAL_FREEZE},
    }
    for a in dataset.accounts:
        allowed = expected.get(status[a.customer_id])
        if allowed is not None:
            assert a.status in allowed, a
        assert (a.status is AccountStatus.CLOSED) == (a.closed_at is not None)


def test_accounts_open_on_or_after_onboarding(dataset: Batch) -> None:
    onboarded = {c.customer_id: c.created_at for c in dataset.customers}

    assert all(onboarded[a.customer_id] <= a.opened_at <= NOW for a in dataset.accounts)


def test_cards_hang_off_transactional_accounts_and_expire_five_years_on(dataset: Batch) -> None:
    accounts = {a.account_id: a for a in dataset.accounts}

    assert 0.6 <= len(dataset.cards) / len(dataset.customers) <= 1.4
    for card in dataset.cards:
        assert accounts[card.account_id].product_code not in _DEPOSITS
        assert card.expiry_year - card.issued_at.year == 5
        assert len(card.pan_last4) == 4
        assert card.pan_last4.isdigit()
        assert card.issued_at >= accounts[card.account_id].opened_at


def test_a_lost_or_expired_card_is_replaced_by_a_newer_one(dataset: Batch) -> None:
    by_account = defaultdict[str, list[CardStatus]](list)
    for card in dataset.cards:
        by_account[card.account_id].append(card.status)

    for statuses in by_account.values():
        if CardStatus.REPLACED in statuses:
            assert len(statuses) >= 2


def test_vpas_are_valid_unique_and_one_primary_per_customer(dataset: Batch) -> None:
    vpas = dataset.vpas
    primary = Counter(v.customer_id for v in vpas if v.is_primary and v.status == "active")

    assert 1.0 <= len(vpas) / len(dataset.customers) <= 1.6
    assert all(is_valid_vpa(v.vpa) and v.vpa.endswith("@kosha") for v in vpas)
    assert len({v.vpa for v in vpas}) == len(vpas)
    assert set(primary.values()) <= {1}


def test_beneficiaries_cool_off_for_a_day_before_turning_active(dataset: Batch) -> None:
    for b in dataset.beneficiaries:
        assert b.cooling_period_ends_at - b.added_at == timedelta(hours=24)
        assert is_valid_ifsc(b.ifsc)
        assert b.account_number_masked.startswith("XXXX")
        in_cooling = b.cooling_period_ends_at > NOW
        assert (b.status is BeneficiaryStatus.PENDING_COOLING) == in_cooling, b


def test_every_customer_has_one_kyc_profile_with_a_legal_history(dataset: Batch) -> None:
    profiles = {k.customer_id: k for k in dataset.kyc_profiles}
    events = defaultdict[str, list[tuple[KycStatus | None, KycStatus]]](list)
    for e in sorted(dataset.kyc_events, key=lambda e: e.occurred_at):
        events[e.kyc_id].append((e.from_status, e.to_status))

    assert set(profiles) == {c.customer_id for c in dataset.customers}
    for profile in profiles.values():
        history = events[profile.kyc_id]
        assert history[0] == (None, KYC_PROFILE.initial)
        for src, dst in history[1:]:
            assert src is not None
            assert KYC_PROFILE.can_transition(src, dst), history
        assert history[-1][1] is profile.kyc_status


def test_verified_profiles_fall_due_for_re_kyc_by_risk_category(dataset: Batch) -> None:
    years = {RiskCategory.HIGH: 2, RiskCategory.MEDIUM: 8, RiskCategory.LOW: 10}
    for k in dataset.kyc_profiles:
        if k.verified_at is None:
            continue
        assert k.next_review_due is not None
        due_in = (k.next_review_due - k.verified_at.date()).days / 365.25
        assert round(due_in) == years[k.risk_category], k
        overdue = k.next_review_due < NOW.date()
        assert overdue == (k.kyc_status in {KycStatus.RE_KYC_DUE, KycStatus.RE_KYC_OVERDUE}), k


def test_aadhaar_and_pan_are_stored_only_as_tokens_and_last_four(dataset: Batch) -> None:
    for k in dataset.kyc_profiles:
        if k.pan_token is not None:
            assert k.pan_last4 is not None
            assert k.pan_last4[:3].isdigit()
            assert k.pan_last4[3].isalpha()
            assert k.pan_token.startswith("kms:")
        if k.aadhaar_ref_token is not None:
            assert k.aadhaar_last4 is not None
            assert k.aadhaar_last4.isdigit()
            assert k.aadhaar_ref_token.startswith("vault:")


def test_kyc_documents_belong_to_their_profile(dataset: Batch) -> None:
    owner = {k.kyc_id: k.customer_id for k in dataset.kyc_profiles}

    assert len(dataset.kyc_documents) >= 3 * len(dataset.customers)
    for d in dataset.kyc_documents:
        assert owner[d.kyc_id] == d.customer_id
        assert len(d.sha256) == 64


def test_every_customer_is_screened_and_peps_match_the_pep_list(dataset: Batch) -> None:
    screened = {s.customer_id for s in dataset.screening_results}
    peps = {k.customer_id for k in dataset.kyc_profiles if k.pep_flag}

    assert screened == {c.customer_id for c in dataset.customers}
    for s in dataset.screening_results:
        if s.customer_id in peps and s.list_source == "internal_pep":
            assert s.decision == "true_match"


_DEPOSITS = {ProductCode.FIXED_DEPOSIT, ProductCode.RECURRING_DEPOSIT}
