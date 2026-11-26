# LLD — `mcp-gateway`

The gateway is the only component MCP clients talk to. It owns the protocol, identity, authorization, data minimisation and the resilience policy toward everything downstream. It holds **no domain state**.

## 1. Module structure

```
services/mcp-gateway/src/mcp_gateway/
├── app.py               # create_app(settings) -> ASGI app; FastMCP server + /healthz + RFC 9728 route
├── server.py            # create_server(settings): pipeline order, tool registration, probes
├── runtime.py           # lifespan: one core-api client per instance; typed accessors for tools
├── settings.py          # pydantic-settings; every timeout and limit is explicit
├── auth/
│   ├── provider.py      # FastMCP Cognito / OAuth-proxy provider wiring
│   ├── principal.py     # Principal(sub, client_id, role, scopes); one Role, scopes capped by it (ADR 0016)
│   └── scopes.py        # Scope, Role, ROLE_SCOPES, ROLE_KB_CEILING, TOOL_SCOPES (plan §4, §6 below)
├── middleware/
│   ├── authorize.py     # stage 4: principal from the token, scope from TOOL_SCOPES (fail closed)
│   ├── rate_limit.py    # DynamoDB token bucket -> 429 + Retry-After
│   ├── deadline.py      # request budget, X-Request-Deadline propagation
│   ├── load_shed.py     # in-flight limit, minimum remaining budget
│   ├── chaos.py         # HMAC-verified fault injection (non-prod + operator scope)
│   └── audit.py         # one audit record per tool call, success or failure
├── tools/
│   ├── common.py        # READ_ONLY annotations, ID types, View base (ignores fields it does not declare)
│   ├── customers.py     # search_customers, get_customer_profile
│   ├── kyc.py           # get_kyc_status, list_kyc_documents
│   ├── payments.py      # get_account_summary, search_transactions, get_transaction, get_spending_insights
│   ├── risk.py          # list_aml_alerts, get_aml_alert, screen_entity
│   ├── writes.py        # raise_dispute, flag_transaction_for_review
│   ├── knowledge.py     # search_knowledge_base, get_document
│   └── ops.py           # get_service_health
├── resources.py         # kb://{department}/{doc_code}, customer://{customer_id}
├── prompts.py           # investigate_suspicious_activity, kyc_periodic_review, dispute_triage
├── masking.py           # role-aware field masking (pure functions)
├── cursors.py           # HMAC-signed opaque pagination cursors
├── errors.py            # error taxonomy; ErrorResults middleware -> isError results with a structured body
└── clients/
    ├── core_api.py      # typed httpx client wrapped in kosha_resilience policies
    └── screening.py     # typed httpx client for screening-sim, behind its own breaker
```

Tools are thin: validate input, check scope, call one `clients.*` method, mask, return. Domain logic lives in `core-api`.

## 2. Request pipeline

```mermaid
flowchart LR
    req["HTTP POST /mcp"] --> shed["1 Load shed<br/>in-flight and budget check"]
    shed --> authn["2 Authenticate<br/>JWT signature, iss, aud, exp"]
    authn --> rl["3 Rate limit<br/>token bucket per verified client_id"]
    rl --> authz["4 Authorize<br/>tool scope check"]
    authz --> chaos["5 Chaos<br/>verify HMAC, arm faults"]
    chaos --> dl["6 Deadline<br/>start budget, trace span"]
    dl --> tool["7 Tool<br/>validate input, call core-api"]
    tool --> mask["8 Mask<br/>per role"]
    mask --> audit["9 Audit<br/>always runs, also on error"]
    audit --> resp["Tool result"]
```

*Notice: the rate limit is keyed on the **verified** `client_id`, so it runs after authentication. Keying on an unverified claim would let a forged token drain a victim's bucket. Unauthenticated floods are absorbed earlier, by API Gateway throttling at the edge, and JWT verification against a cached JWKS is cheap. Audit runs in a `finally`, so denied and failed calls are recorded too.*

| Order | Stage | Rejects with | Notes |
|---|---|---|---|
| 1 | Load shed | `503` + `Retry-After` | In-flight > `MAX_IN_FLIGHT` or no usable budget |
| 2 | Authenticate | `401` + `WWW-Authenticate` with `resource_metadata` | JWKS cached 10 min, refreshed on unknown `kid` |
| 3 | Rate limit | `429` + `Retry-After` | Token bucket keyed by the verified `client_id` (DynamoDB conditional update) |
| 4 | Authorize | tool error `forbidden` (`403` semantics) | Scope from `TOOL_SCOPES`; KB ceiling from role |
| 5 | Chaos | ignored if invalid | Only honoured when `CHAOS_ENABLED` and principal has the operator role |
| 6 | Deadline | — | Budget = `min(client hint, TOOL_BUDGET[tool])` |
| 7 | Tool | per taxonomy | Pydantic validation errors map to `invalid_argument` |
| 8 | Mask | — | Pure function of (payload, principal) |
| 9 | Audit | — | Write failure is logged and metered, never fails the call |

## 3. Tool contract template

Every tool follows the same shape so it can be tested the same way.

```python
class TransactionSearch(View):  # View: frozen, ignores fields it does not declare
    items: list[TransactionView]
    next_cursor: str | None
    truncated: bool
    as_of: datetime


async def search_transactions(
    ctx: Context,
    account_id: AccountId,  # Annotated[str, Field(pattern=...)]: checked before any call
    *,
    initiated_from: AwareDatetime | None = None,  # ISO 8601 with an offset
    initiated_before: AwareDatetime | None = None,
    min_amount_paise: Annotated[int | None, Field(gt=0)] = None,
    statuses: list[TransactionStatus] | None = None,  # sorted before the cursor hashes it
    limit: Annotated[int, Field(ge=1, le=100)] = 25,  # not part of the cursor's query
    cursor: str | None = None,
) -> TransactionSearch:
    """Transactions on one Account, newest first (the docstring is the tool description)."""
    caller = await principal(ctx)  # resolved and scope-checked by Authorize (stage 4)
    page = await core_api(ctx).get(
        caller.signed_as(), f"/v1/accounts/{account_id}/transactions", TransactionSearch, params=...
    )
    return mask(page, caller.scopes)


def register(mcp: FastMCP) -> None:
    mcp.tool(search_transactions, title="Search transactions", annotations=READ_ONLY)
```

| Rule | Reason |
|---|---|
| Flat, annotated arguments | The input schema an agent sees is the argument list itself; cross-field rules (a range, "at least one criterion") are checked in the tool and raise `invalid_argument` |
| Strict input validation | FastMCP's `strict_input_validation`: unknown or mistyped arguments are rejected, not ignored or coerced |
| The scope lives in `TOOL_SCOPES`, not in the tool | `Authorize` checks it before the tool runs; a tool missing from the table cannot be called, and a guard test requires every registered tool to be listed |
| Money in paise (`int`) with a display string alongside | No floats anywhere on the wire |
| Output models are explicit | FastMCP publishes them as `outputSchema`; contract tests snapshot them |
| Write tools take `idempotency_key: UUID` | Required, not optional; one key per intended write, reused on every retry of it |
| A write is retried by the gateway only with its original key (2 attempts, on connect errors, timeouts, `503`, `504`) | A response lost after `core-api` committed comes back as the stored replay, not a second dispute ([System design §8](../system-design.md#8-idempotency-end-to-end)) |
| The audit middleware mints `audit_id` once per tool call | `POST /v1/audit` inserts with `ON CONFLICT DO NOTHING`, so a retried audit write records the call once |
| Write tools carry `destructiveHint: False, idempotentHint: True` | Accurate hints help clients decide when to confirm |
| Write tools request confirmation via MCP elicitation when the client supports it | Falls back to an explicit `confirm: true` argument |

## 4. Error taxonomy

Tool failures are returned as MCP tool results with `isError: true` and a structured body, so the model can reason about them. Protocol-level failures use HTTP status codes.

| Code | Raised when | HTTP / MCP | Retry hint to client |
|---|---|---|---|
| `unauthenticated` | Missing, expired, malformed token; wrong `aud` or `iss` | HTTP 401 + `WWW-Authenticate` | Re-authenticate |
| `forbidden` | Scope missing; KB ceiling exceeded | Tool error | No |
| `invalid_argument` | Pydantic validation failed; tampered cursor | Tool error | No (fix input) |
| `not_found` | Entity absent or not visible to caller | Tool error | No |
| `conflict` | Idempotency key reused with different payload; illegal state transition | Tool error | No |
| `rate_limited` | Token bucket empty | HTTP 429 + `Retry-After` | Yes, after delay |
| `overloaded` | Load shed | HTTP 503 + `Retry-After` | Yes, after delay |
| `deadline_exceeded` | Budget exhausted | Tool error | Yes, once |
| `dependency_unavailable` | Breaker open or downstream 5xx after retries | Tool error with `dependency` field | Yes, after delay |
| `degraded` | Not an error: result flagged `degraded: true` | Success | n/a |
| `internal` | Anything unexpected | Tool error, generic message, `trace_id` only | Yes, once |

Error bodies never contain stack traces, SQL, or upstream payloads. They always contain `code`, `message`, `trace_id`, and optionally `retry_after_s` and `dependency`.

## 5. Pagination cursors

Cursors are opaque to clients and tamper-evident.

| Field | Content |
|---|---|
| `v` | Format version |
| `k` | Keyset position, e.g. `(initiated_at, txn_id)` of last row |
| `q` | SHA-256 of the canonical query (filters) the cursor belongs to |
| `sub` | Subject the cursor was issued to |
| `exp` | Expiry (15 minutes) |
| `sig` | HMAC-SHA256 over the above with a key from Secrets Manager |

Encoding: `base64url(json(payload)) + "." + base64url(sig)`. Verification failures, a different query hash, a different subject, or expiry all produce `invalid_argument`. Keyset pagination keeps deep pages as fast as the first.

## 6. Tool scopes

| Tool | Required scope | Reads PII | Notes |
|---|---|---|---|
| `search_customers` | `customers:read` | masked | Name / CIF / mobile-last-4 search |
| `get_customer_profile` | `customers:read` | masked unless `kyc:pii` | |
| `get_kyc_status` | `kyc:read` | masked | PAN and Aadhaar masked to the last 4; the full PAN only when a `kyc:pii` holder passes `reveal_pan: true`, which calls core-api's audited `/kyc/pan` |
| `list_kyc_documents` | `kyc:read` | no | Metadata only, never document bytes |
| `get_account_summary` | `transactions:read` | account number always masked; own VPAs masked | Balances with `*_display` strings |
| `search_transactions` | `transactions:read` | counterparty masked | Signed cursor bound to the filters and the caller; `amount_display` beside `amount_paise` |
| `get_transaction` | `transactions:read` | counterparty masked; device and location withheld | Includes status history |
| `get_spending_insights` | `transactions:read` | no | Aggregates only |
| `list_aml_alerts` | `aml:read` | masked | Soonest SLA first; signed cursor over `(sla_due_at, alert_id)` bound to the filters and the caller |
| `get_aml_alert` | `aml:read` | masked | Rule thresholds, narrative and the triggering Transactions in the payments view (counterparties visible with `aml:read`; no device detail) |
| `screen_entity` | `screening:run` | n/a | Behind vendor breaker; `status: deferred` when open |
| `raise_dispute` | `disputes:write` | n/a | Idempotent, audited, emits outbox event |
| `flag_transaction_for_review` | `reviews:write` | n/a | Idempotent, audited, emits outbox event |
| `search_knowledge_base` | `kb:read` | n/a | Results limited by role ceiling via RLS |
| `get_document` | `kb:read` | n/a | Same ceiling |
| `get_service_health` | `customers:read` | n/a | Breaker states, dependency latency |

## 7. Masking rules

| Field | Masked form | Unmasked with |
|---|---|---|
| PAN | `******234X` (last 4 kept) | `kyc:pii` **and** an explicit `reveal_pan` (each reveal is audited) |
| Aadhaar | always `XXXX XXXX 1234` | never (only last 4 is stored) |
| Mobile | `******7890` | `kyc:pii` |
| Email | `r****@example.com` | `kyc:pii` |
| Account number | `XXXXXX4321` | never via MCP |
| Counterparty VPA | `ra***@okaxis` | `aml:read` |
| Customer's own VPA | `98***@kosha` (often the mobile number itself) | `kyc:pii` |
| Device ID, IP address, latitude, longitude of a Transaction | withheld (`null`); the city stays | `aml:read` |
| Date of birth | year only | `kyc:pii` |

Masking is a pure function tested exhaustively with property tests: for every role and every view model, no field outside the role's allowance survives. Rules are declared on field types (`Mobile`, `OwnVpa`, `Annotated[str | None, AML_ONLY]`, ...); a `Masked` rule shows a masked form, a `Withheld` rule removes the value.
