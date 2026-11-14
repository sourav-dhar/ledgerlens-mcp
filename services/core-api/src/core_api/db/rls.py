"""Who a unit of work acts for, as row-level security policies and the audit trail see it."""

from dataclasses import dataclass

from kosha_domain.vocabulary import Classification


@dataclass(frozen=True, slots=True)
class Caller:
    """The verified principal a request acts for, as forwarded by the gateway.

    ``actor`` lands in ``kosha.actor``; ``kb_ceiling`` in ``kosha.kb_ceiling``, which the
    knowledge-base policies compare against. No ceiling means no knowledge-base rows.
    """

    actor: str
    kb_ceiling: Classification | None = None


# One round trip sets every transaction-local setting. ``set_config(..., true)`` is
# ``SET LOCAL``: it ends with the transaction, so a pooled connection never carries one
# caller's identity into the next caller's request. Setting ``role`` checks membership.
CONTEXT_SQL = """
    SELECT set_config('role', %(role)s, true),
           set_config('transaction_read_only', %(read_only)s, true),
           set_config('statement_timeout', %(statement_timeout)s, true),
           set_config('kosha.actor', %(actor)s, true),
           set_config('kosha.kb_ceiling', %(kb_ceiling)s, true)
"""


def context_params(
    caller: Caller, *, role: str, read_only: bool, statement_timeout_ms: int
) -> dict[str, str]:
    return {
        "role": role,
        "read_only": "on" if read_only else "off",
        "statement_timeout": str(statement_timeout_ms),
        "actor": caller.actor,
        "kb_ceiling": caller.kb_ceiling.value if caller.kb_ceiling else "",
    }
