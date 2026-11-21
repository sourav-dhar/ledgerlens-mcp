"""Scopes, Roles and what each Role may do (plan v1.0 §4).

`tests/test_auth.py` reads the plan's table and requires these mappings to equal it.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from kosha_domain.vocabulary import Classification


class Scope(StrEnum):
    CUSTOMERS_READ = "customers:read"
    TRANSACTIONS_READ = "transactions:read"
    KYC_READ = "kyc:read"
    KYC_PII = "kyc:pii"
    """Unmasked PAN and contact details."""
    AML_READ = "aml:read"
    SCREENING_RUN = "screening:run"
    DISPUTES_WRITE = "disputes:write"
    REVIEWS_WRITE = "reviews:write"
    KB_READ = "kb:read"


class Role(StrEnum):
    """The job function a Staff member performs (see GLOSSARY: Role)."""

    SUPPORT_AGENT = "support_agent"
    ANALYST = "analyst"
    COMPLIANCE_OFFICER = "compliance_officer"
    DEMO_READONLY = "demo_readonly"


_READ_EVERYDAY = frozenset(
    {Scope.CUSTOMERS_READ, Scope.TRANSACTIONS_READ, Scope.KYC_READ, Scope.KB_READ}
)
_INVESTIGATE = frozenset({Scope.AML_READ, Scope.SCREENING_RUN, Scope.REVIEWS_WRITE})

ROLE_SCOPES: Mapping[Role, frozenset[Scope]] = MappingProxyType(
    {
        Role.SUPPORT_AGENT: _READ_EVERYDAY | {Scope.DISPUTES_WRITE},
        Role.ANALYST: _READ_EVERYDAY | _INVESTIGATE,
        Role.COMPLIANCE_OFFICER: _READ_EVERYDAY
        | _INVESTIGATE
        | {Scope.KYC_PII, Scope.DISPUTES_WRITE},
        Role.DEMO_READONLY: _READ_EVERYDAY,
    }
)
"""The most each Role may do; a token can only narrow it."""

ROLE_KB_CEILING: Mapping[Role, Classification] = MappingProxyType(
    {
        Role.SUPPORT_AGENT: Classification.INTERNAL,
        Role.ANALYST: Classification.CONFIDENTIAL,
        Role.COMPLIANCE_OFFICER: Classification.RESTRICTED,
        Role.DEMO_READONLY: Classification.PUBLIC,
    }
)
"""The most sensitive Documents each Role may read; enforced by row-level security."""
