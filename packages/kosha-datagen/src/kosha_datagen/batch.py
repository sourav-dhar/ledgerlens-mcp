"""A batch of rows, grouped by table and listed in an order foreign keys can load in."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, fields
from typing import Any, NamedTuple

from kosha_datagen import rows


@dataclass(frozen=True, slots=True)
class TableRows:
    """The rows bound for one table, with the columns they fill."""

    table: str
    columns: tuple[str, ...]
    rows: list[Any]


@dataclass(slots=True)
class Batch:
    """Rows that commit together. Field order is load order: referenced tables come first."""

    merchants: list[rows.Merchant] = field(default_factory=list[rows.Merchant])
    aml_rules: list[rows.AmlRule] = field(default_factory=list[rows.AmlRule])
    customers: list[rows.Customer] = field(default_factory=list[rows.Customer])
    addresses: list[rows.Address] = field(default_factory=list[rows.Address])
    accounts: list[rows.Account] = field(default_factory=list[rows.Account])
    cards: list[rows.Card] = field(default_factory=list[rows.Card])
    vpas: list[rows.Vpa] = field(default_factory=list[rows.Vpa])
    beneficiaries: list[rows.Beneficiary] = field(default_factory=list[rows.Beneficiary])
    kyc_profiles: list[rows.KycProfile] = field(default_factory=list[rows.KycProfile])
    kyc_documents: list[rows.KycDocument] = field(default_factory=list[rows.KycDocument])
    kyc_events: list[rows.KycEvent] = field(default_factory=list[rows.KycEvent])
    screening_results: list[rows.ScreeningResult] = field(
        default_factory=list[rows.ScreeningResult]
    )
    transactions: list[rows.Transaction] = field(default_factory=list[rows.Transaction])
    transaction_status_history: list[rows.TransactionStatusChange] = field(
        default_factory=list[rows.TransactionStatusChange]
    )
    journal_entries: list[rows.JournalEntry] = field(default_factory=list[rows.JournalEntry])
    postings: list[rows.Posting] = field(default_factory=list[rows.Posting])
    aml_alerts: list[rows.AmlAlert] = field(default_factory=list[rows.AmlAlert])
    disputes: list[rows.Dispute] = field(default_factory=list[rows.Dispute])
    transaction_reviews: list[rows.TransactionReview] = field(
        default_factory=list[rows.TransactionReview]
    )

    def tables(self) -> Iterator[TableRows]:
        """Each non-empty table's rows, in load order."""
        for f in fields(self):
            batch_rows: list[NamedTuple] = getattr(self, f.name)
            if batch_rows:
                yield TableRows(_TABLES[f.name], batch_rows[0]._fields, batch_rows)

    def extend(self, other: "Batch") -> None:
        for f in fields(self):
            getattr(self, f.name).extend(getattr(other, f.name))

    def row_count(self) -> int:
        return sum(len(t.rows) for t in self.tables())

    @classmethod
    def merge(cls, batches: Iterable["Batch"]) -> "Batch":
        merged = cls()
        for batch in batches:
            merged.extend(batch)
        return merged


_TABLES = {
    "merchants": "core.merchants",
    "aml_rules": "risk.aml_rules",
    "customers": "core.customers",
    "addresses": "core.addresses",
    "accounts": "core.accounts",
    "cards": "core.cards",
    "vpas": "core.vpas",
    "beneficiaries": "core.beneficiaries",
    "kyc_profiles": "kyc.kyc_profiles",
    "kyc_documents": "kyc.kyc_documents",
    "kyc_events": "kyc.kyc_events",
    "screening_results": "risk.screening_results",
    "transactions": "core.transactions",
    "transaction_status_history": "core.transaction_status_history",
    "journal_entries": "ledger.journal_entries",
    "postings": "ledger.postings",
    "aml_alerts": "risk.aml_alerts",
    "disputes": "ops.disputes",
    "transaction_reviews": "ops.transaction_reviews",
}
