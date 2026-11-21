"""Who a verified token acts for, in which Role, with which scopes (plan v1.0 §4, ADR 0016).

Every principal acts in exactly one Role: a Staff member's comes from their Cognito group,
a service client's from configuration. The token's scopes are capped by the Role's, so a
client allowed `kyc:pii` still cannot unmask for a support agent.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from fastmcp.server.auth import AccessToken

from kosha_domain.vocabulary import Classification
from mcp_gateway.auth.principal import Principal, principal_from
from mcp_gateway.auth.scopes import ROLE_KB_CEILING, ROLE_SCOPES, Role, Scope
from mcp_gateway.errors import ForbiddenError

PLAN = Path(__file__).parents[3] / "docs" / "plans" / "v1.0-architecture.md"
ALL_SCOPES = " ".join(scope.value for scope in Scope)
NO_MACHINES: dict[str, Role] = {}


def _token(
    scopes: str = ALL_SCOPES, *, groups: list[str] | None = None, **claims: Any
) -> AccessToken:
    claims = {"sub": "staff-0042", "client_id": "console", "scope": scopes, **claims}
    if groups is not None:
        claims["cognito:groups"] = groups
    return AccessToken(
        token="opaque-test-token",  # noqa: S106 — never verified; claims are given directly
        client_id=claims["client_id"],
        scopes=scopes.split(),
        claims=claims,
    )


def _plan_table() -> tuple[dict[Role, frozenset[Scope]], dict[Role, Classification]]:
    """The Scopes and roles table of plan v1.0 §4, read from the accepted plan."""
    section = PLAN.read_text(encoding="utf-8").split("### Scopes and roles", 1)[1]
    rows = [line for line in section.splitlines() if line.startswith("| `")]
    header = next(line for line in section.splitlines() if line.startswith("| Scope"))
    roles = [Role(cell.strip()) for cell in header.strip("|").split("|")[1:]]
    scopes: dict[Role, set[Scope]] = {role: set() for role in roles}
    ceilings: dict[Role, Classification] = {}
    for row in rows:
        first, *cells = (cell.strip() for cell in row.strip("|").split("|"))
        scope = Scope(re.findall(r"`([^`]+)`", first)[0])
        for role, cell in zip(roles, cells, strict=True):
            if cell == "✓":
                scopes[role].add(scope)
            elif cell:
                scopes[role].add(scope)
                ceilings[role] = Classification(cell)
    return {role: frozenset(s) for role, s in scopes.items()}, ceilings


def test_the_role_table_is_the_accepted_plans() -> None:
    scopes, ceilings = _plan_table()

    assert dict(ROLE_SCOPES) == scopes
    assert dict(ROLE_KB_CEILING) == ceilings


def test_a_staff_members_role_comes_from_their_group() -> None:
    principal = principal_from(_token(groups=["analyst"]), machine_roles=NO_MACHINES)

    assert principal == Principal(
        sub="staff-0042",
        client_id="console",
        role=Role.ANALYST,
        scopes=ROLE_SCOPES[Role.ANALYST],
    )


def test_scopes_the_role_lacks_are_dropped() -> None:
    principal = principal_from(_token(groups=["support_agent"]), machine_roles=NO_MACHINES)

    assert Scope.KYC_PII not in principal.scopes
    assert principal.scopes == ROLE_SCOPES[Role.SUPPORT_AGENT]


def test_scopes_the_token_lacks_are_not_granted() -> None:
    principal = principal_from(
        _token("customers:read", groups=["compliance_officer"]), machine_roles=NO_MACHINES
    )

    assert principal.scopes == {Scope.CUSTOMERS_READ}


def test_unknown_scopes_and_groups_are_ignored() -> None:
    token = _token("customers:read openid admin:all", groups=["eu-north-1_Google", "analyst"])

    principal = principal_from(token, machine_roles=NO_MACHINES)

    assert (principal.role, principal.scopes) == (Role.ANALYST, {Scope.CUSTOMERS_READ})


def test_a_service_clients_role_comes_from_configuration() -> None:
    token = _token(sub="e2e-runner", client_id="e2e-runner")

    principal = principal_from(token, machine_roles={"e2e-runner": Role.DEMO_READONLY})

    assert (principal.sub, principal.role) == ("e2e-runner", Role.DEMO_READONLY)


def test_a_group_outranks_configuration() -> None:
    token = _token(groups=["support_agent"], client_id="e2e-runner")

    principal = principal_from(token, machine_roles={"e2e-runner": Role.COMPLIANCE_OFFICER})

    assert principal.role is Role.SUPPORT_AGENT


@pytest.mark.parametrize("groups", [None, [], ["eu-north-1_Google"], ["analyst", "support_agent"]])
def test_a_principal_without_exactly_one_role_is_refused(groups: list[str] | None) -> None:
    with pytest.raises(ForbiddenError, match="exactly one role"):
        principal_from(_token(groups=groups), machine_roles=NO_MACHINES)


def test_without_a_sub_the_client_acts_for_itself() -> None:
    token = _token(groups=["analyst"])
    del token.claims["sub"]

    assert principal_from(token, machine_roles=NO_MACHINES).sub == "console"


@pytest.mark.parametrize(
    ("role", "ceiling"),
    [
        (Role.SUPPORT_AGENT, Classification.INTERNAL),
        (Role.ANALYST, Classification.CONFIDENTIAL),
        (Role.COMPLIANCE_OFFICER, Classification.RESTRICTED),
        (Role.DEMO_READONLY, Classification.PUBLIC),
    ],
)
def test_core_api_acts_for_the_sub_with_the_roles_ceiling(
    role: Role, ceiling: Classification
) -> None:
    principal = principal_from(_token(groups=[role.value]), machine_roles=NO_MACHINES)

    signed = principal.signed_as()

    assert (signed.actor, signed.kb_ceiling) == ("staff-0042", ceiling)


def test_without_kb_read_core_api_gets_no_ceiling_and_returns_no_documents() -> None:
    principal = principal_from(_token("customers:read", groups=["analyst"]), machine_roles={})

    assert principal.signed_as().kb_ceiling is None


def test_require_passes_a_granted_scope_and_refuses_a_missing_one() -> None:
    principal = principal_from(_token(groups=["support_agent"]), machine_roles=NO_MACHINES)

    principal.require(Scope.CUSTOMERS_READ)
    with pytest.raises(ForbiddenError, match="aml:read"):
        principal.require(Scope.AML_READ)
