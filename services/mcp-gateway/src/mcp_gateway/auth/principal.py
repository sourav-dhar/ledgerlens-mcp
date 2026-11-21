"""The principal a verified access token acts for (ADR 0016).

Every principal acts in exactly one Role. A Staff member's comes from their Cognito group;
a service client using client credentials has no group, so its Role is configured by
``client_id``. Effective scopes are the token's scopes capped by the Role's: the token says
what the client application may do, the Role what the person (or service) may do, and a
call needs both. Anything without exactly one Role is refused, so a misconfigured user or
client fails closed rather than inheriting every scope its client was granted.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from fastmcp.server.auth import AccessToken

from kosha_domain import signing
from kosha_domain.vocabulary import Classification
from mcp_gateway.auth.scopes import ROLE_KB_CEILING, ROLE_SCOPES, Role, Scope
from mcp_gateway.errors import ForbiddenError

GROUPS_CLAIM = "cognito:groups"

_ROLES = {role.value: role for role in Role}
_SCOPES = {scope.value: scope for scope in Scope}


@dataclass(frozen=True, slots=True)
class Principal:
    sub: str
    """Who acts: a Staff member, or a service client acting for itself."""
    client_id: str
    """The OAuth client (application) they act through."""
    role: Role
    scopes: frozenset[Scope]
    """Effective scopes: granted to the token and allowed to the Role."""

    @property
    def kb_ceiling(self) -> Classification | None:
        """The most sensitive Documents this principal may read; ``None`` without ``kb:read``."""
        return ROLE_KB_CEILING[self.role] if Scope.KB_READ in self.scopes else None

    def require(self, scope: Scope) -> None:
        if scope not in self.scopes:
            msg = f"the {scope.value} scope is required"
            raise ForbiddenError(msg)

    def signed_as(self) -> signing.Principal:
        """Whom core-api acts for: the ``sub``, and the ceiling its row-level security applies."""
        return signing.Principal(actor=self.sub, kb_ceiling=self.kb_ceiling)


def _groups(claims: Mapping[str, Any]) -> list[str]:
    value = claims.get(GROUPS_CLAIM)
    if not isinstance(value, list):
        return []
    return [group for group in cast("list[object]", value) if isinstance(group, str)]


def _role(claims: Mapping[str, Any], client_id: str, machine_roles: Mapping[str, Role]) -> Role:
    named = {_ROLES[group] for group in _groups(claims) if group in _ROLES}
    if not named and client_id in machine_roles:
        return machine_roles[client_id]
    if len(named) != 1:
        msg = "a principal must act in exactly one role; ask an administrator to assign one"
        raise ForbiddenError(msg)
    return named.pop()


def principal_from(token: AccessToken, *, machine_roles: Mapping[str, Role]) -> Principal:
    """The principal ``token`` acts for.

    Raises:
        ForbiddenError: if the token's subject holds no Role, or more than one.
    """
    claims = token.claims or {}
    role = _role(claims, token.client_id, machine_roles)
    granted = {_SCOPES[s] for s in token.scopes if s in _SCOPES}
    sub = token.subject or claims.get("sub") or token.client_id
    return Principal(
        sub=str(sub),
        client_id=token.client_id,
        role=role,
        scopes=frozenset(granted) & ROLE_SCOPES[role],
    )
