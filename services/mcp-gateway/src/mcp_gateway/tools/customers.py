"""Customer tools: `search_customers` and `get_customer_profile` (LLD §6)."""

from datetime import date, datetime
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from kosha_domain.vocabulary import (
    AddressType,
    CustomerStatus,
    Gender,
    IncomeBand,
    OnboardingChannel,
    Persona,
    ResidentialStatus,
    RiskCategory,
    Segment,
)
from mcp_gateway.errors import InvalidArgumentError
from mcp_gateway.masking import BirthDate, Email, Mobile, mask
from mcp_gateway.runtime import core_api, principal
from mcp_gateway.tools.common import READ_ONLY, CustomerId, View


class CustomerSummary(View):
    """One search hit: enough to tell Customers apart and pick one."""

    customer_id: str
    cif_number: str
    full_name: str
    mobile: Mobile
    segment: Segment
    status: CustomerStatus


class CustomerSearch(View):
    customers: list[CustomerSummary]
    """In name order."""


class Address(View):
    address_id: str
    address_type: AddressType
    line1: str
    line2: str | None
    city: str
    district: str | None
    state: str
    state_code: str
    pincode: str
    country: str
    is_verified: bool
    valid_from: date
    valid_to: date | None


class CustomerProfile(View):
    customer_id: str
    cif_number: str
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: BirthDate
    gender: Gender
    email: Email | None
    mobile: Mobile
    mobile_verified: bool
    persona: Persona
    occupation: str | None
    employer_name: str | None
    annual_income_band: IncomeBand | None
    segment: Segment
    residential_status: ResidentialStatus
    preferred_language: str
    onboarding_channel: OnboardingChannel
    relationship_start_date: date
    status: CustomerStatus
    risk_category: RiskCategory
    created_at: datetime
    updated_at: datetime
    addresses: list[Address]
    """Addresses in force today, permanent first."""


async def search_customers(
    ctx: Context,
    name: Annotated[
        str | None,
        Field(min_length=2, max_length=64, description="Part of the first and last name."),
    ] = None,
    cif_number: Annotated[
        str | None, Field(pattern=r"^\d{10}$", description="The 10-digit CIF number.")
    ] = None,
    mobile_last4: Annotated[
        str | None, Field(pattern=r"^\d{4}$", description="Last four digits of the mobile.")
    ] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> CustomerSearch:
    """Find Customers matching every criterion given: name, CIF number, mobile's last four.

    Mobile numbers are masked unless you hold kyc:pii.
    """
    if name is None and cif_number is None and mobile_last4 is None:
        msg = "give at least one of name, cif_number or mobile_last4"
        raise InvalidArgumentError(msg)
    caller = await principal(ctx)
    found = await core_api(ctx).get(
        caller.signed_as(),
        "/v1/customers",
        CustomerSearch,
        params={
            "name": name,
            "cif_number": cif_number,
            "mobile_last4": mobile_last4,
            "limit": limit,
        },
    )
    return mask(found, caller.scopes)


async def get_customer_profile(ctx: Context, customer_id: CustomerId) -> CustomerProfile:
    """A Customer's profile with the Addresses in force today.

    Mobile, email and date of birth (year only) are masked unless you hold kyc:pii.
    """
    caller = await principal(ctx)
    profile = await core_api(ctx).get(
        caller.signed_as(), f"/v1/customers/{customer_id}", CustomerProfile
    )
    return mask(profile, caller.scopes)


def register(mcp: FastMCP) -> None:
    mcp.tool(search_customers, title="Search customers", annotations=READ_ONLY)
    mcp.tool(get_customer_profile, title="Customer profile", annotations=READ_ONLY)
