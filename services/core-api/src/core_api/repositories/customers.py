"""Customers and their Addresses."""

from dataclasses import dataclass

from psycopg import sql

from core_api.db import Connection
from core_api.schemas.customers import Address, CustomerProfile, CustomerSummary

_PROFILE = """
    SELECT customer_id, cif_number, first_name, middle_name, last_name, date_of_birth,
           gender, email, mobile, mobile_verified, persona, occupation, employer_name,
           annual_income_band, segment, residential_status, preferred_language,
           onboarding_channel, relationship_start_date, status, risk_category,
           created_at, updated_at
    FROM core.customers
    WHERE customer_id = %s
"""

# Addresses in force today; the enum orders permanent before correspondence.
_ADDRESSES = """
    SELECT address_id, address_type, line1, line2, city, district, state, state_code,
           pincode, country, is_verified, valid_from, valid_to
    FROM core.addresses
    WHERE customer_id = %s AND (valid_to IS NULL OR valid_to >= current_date)
    ORDER BY address_type, valid_from DESC, address_id
"""

_SUMMARY = sql.SQL("""
    SELECT customer_id, cif_number,
           concat_ws(' ', first_name, middle_name, last_name) AS full_name,
           mobile, segment, status
    FROM core.customers
    WHERE {conditions}
    ORDER BY last_name, first_name, customer_id
    LIMIT %(limit)s
""")


@dataclass(frozen=True, slots=True)
class CustomerSearch:
    """Criteria are combined with AND; at least one must be given."""

    name: str | None = None
    cif_number: str | None = None
    mobile_last4: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.name is None and self.cif_number is None and self.mobile_last4 is None


def _contains(term: str) -> str:
    """An ILIKE pattern matching ``term`` anywhere, with its own wildcards made literal."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class CustomerRepository:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    async def profile(self, customer_id: str) -> CustomerProfile | None:
        row = await (await self._conn.execute(_PROFILE, [customer_id])).fetchone()
        if row is None:
            return None
        addresses = await (await self._conn.execute(_ADDRESSES, [customer_id])).fetchall()
        return CustomerProfile.model_validate(
            row | {"addresses": [Address.model_validate(a) for a in addresses]}
        )

    async def search(self, criteria: CustomerSearch, *, limit: int) -> list[CustomerSummary]:
        conditions: list[sql.Composable] = []
        params: dict[str, object] = {"limit": limit}
        if criteria.name is not None:
            # Served by the trigram index customers_name_trgm_idx.
            conditions.append(sql.SQL("(first_name || ' ' || last_name) ILIKE %(name)s"))
            params["name"] = _contains(criteria.name)
        if criteria.cif_number is not None:
            conditions.append(sql.SQL("cif_number = %(cif_number)s"))
            params["cif_number"] = criteria.cif_number
        if criteria.mobile_last4 is not None:
            conditions.append(sql.SQL("right(mobile, 4) = %(mobile_last4)s"))
            params["mobile_last4"] = criteria.mobile_last4
        query = _SUMMARY.format(conditions=sql.SQL(" AND ").join(conditions))
        rows = await (await self._conn.execute(query, params)).fetchall()
        return [CustomerSummary.model_validate(r) for r in rows]
