"""Idempotent writes: the key, the business change and the response commit together (ADR 0007).

A write first claims its key inside the unit of work. A concurrent request with the same
key blocks on that row until the first commits, then finds it completed and replays the
stored response; if the first rolls back, the key is free again. So a retried request
never applies twice, and never sees a different answer.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from core_api.db import Connection
from core_api.errors import ConflictError

KEY_TTL = timedelta(hours=24)

# A key whose record has expired may be claimed again; otherwise the insert does nothing
# and the existing record decides the outcome.
_CLAIM = """
    INSERT INTO ops.idempotency_keys AS k (scope, key, request_hash, status, expires_at)
    VALUES (%(scope)s, %(key)s, %(request_hash)s, 'in_progress', now() + %(ttl)s)
    ON CONFLICT (scope, key) DO UPDATE
        SET request_hash = EXCLUDED.request_hash, status = 'in_progress', response = NULL,
            created_at = now(), expires_at = EXCLUDED.expires_at
        WHERE k.expires_at <= now()
    RETURNING k.key
"""

_EXISTING = """
    SELECT request_hash, status::text AS status, response
    FROM ops.idempotency_keys
    WHERE scope = %(scope)s AND key = %(key)s
"""

_COMPLETE = """
    UPDATE ops.idempotency_keys
    SET status = 'completed', response = %(response)s
    WHERE scope = %(scope)s AND key = %(key)s
"""


def request_hash(actor: str, request: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the request and the caller who sent it."""
    canonical = json.dumps(
        {"actor": actor, "request": request}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Written[M: BaseModel]:
    value: M
    replayed: bool
    """True when ``value`` is the stored response to an earlier request with this key."""


async def idempotent[M: BaseModel](
    conn: Connection,
    *,
    scope: str,
    key: str,
    actor: str,
    request: BaseModel,
    result: type[M],
    perform: Callable[[], Awaitable[M]],
) -> Written[M]:
    """Run ``perform`` once per ``(scope, key)``, or replay what it returned the first time.

    Raises:
        ConflictError: if the key was used for a different request (or by a different
            caller), or that request is somehow still in progress.
    """
    params: dict[str, Any] = {
        "scope": scope,
        "key": key,
        "request_hash": request_hash(actor, request.model_dump(mode="json")),
        "ttl": KEY_TTL,
    }
    claimed = await (await conn.execute(_CLAIM, params)).fetchone()
    if claimed is None:
        existing = await (await conn.execute(_EXISTING, params)).fetchone()
        if existing is None:  # pragma: no cover — the row conflicted, so it exists
            msg = "the Idempotency-Key record vanished; retry"
            raise ConflictError(msg)
        if existing["request_hash"] != params["request_hash"]:
            msg = "this Idempotency-Key was already used for a different request"
            raise ConflictError(msg)
        if existing["status"] != "completed":  # pragma: no cover — never committed
            msg = "a request with this Idempotency-Key is still in progress; retry shortly"
            raise ConflictError(msg)
        return Written(result.model_validate(existing["response"]), replayed=True)

    value = await perform()
    await conn.execute(_COMPLETE, params | {"response": Jsonb(value.model_dump(mode="json"))})
    return Written(value, replayed=False)
