"""Customer resources as the API returns them. Values are unmasked: the gateway masks."""

from datetime import date, datetime

from pydantic import BaseModel

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


class Address(BaseModel):
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


class CustomerSummary(BaseModel):
    """One search hit: enough to tell Customers apart and pick one."""

    customer_id: str
    cif_number: str
    full_name: str
    mobile: str
    segment: Segment
    status: CustomerStatus


class CustomerProfile(BaseModel):
    customer_id: str
    cif_number: str
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date
    gender: Gender
    email: str | None
    mobile: str
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


class CustomerSearchResult(BaseModel):
    customers: list[CustomerSummary]
