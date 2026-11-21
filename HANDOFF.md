# Handoff

> Read at the start of every session; rewrite at the end of every session. Durable lessons go to [MEMORY.md](MEMORY.md), standing rules to [CLAUDE.md](CLAUDE.md).

**Last updated:** 2026-11-21 · **Current release:** v0.2.0 (v0.3.0 pending in #3) · **Phase in progress:** P3 MCP gateway, foundation merged (#23) · **Next:** P3 continued: the remaining tools, then JWT, rate limits and audit

## Where things stand

P2 is complete (see the core-api LLD §8 failure matrix). P3's foundation landed in #23. Every tool built on it follows LLD §3, and its pieces are:

| Piece | Module | What it guarantees |
|---|---|---|
| Error taxonomy | `errors.py` | Every failure is an `isError` result with `{"error": {code, message, trace_id, retry_after_s?, dependency?}}`; validation errors name the field without echoing the value; anything unexpected is `internal` with only a trace ID |
| core-api client | `clients/core_api.py` | Signs the final encoded target per attempt (ADR 0013); maps core-api codes to the taxonomy (`401` from core-api is `internal`: a key mismatch); retries connect errors, timeouts, `503`, `504` once, writes only with their original `Idempotency-Key` |
| Principal | `auth/principal.py`, `auth/scopes.py` | Exactly one Role per principal (Cognito group, or `MACHINE_CLIENT_ROLES` for service clients); scopes = token ∩ Role ([ADR 0016](docs/adr/0016-one-role-per-principal-scopes-capped-by-role.md)); KB ceiling sent only with `kb:read`. The role table is tested against plan v1.0 §4 |
| Authorization | `middleware/authorize.py` | Stage 4: principal resolved once per call; scope from `TOOL_SCOPES` (all 16 tools, tested against LLD §6); an unlisted tool is refused; no identity is `unauthenticated` |
| Masking | `masking.py` | Rules declared on field types (`Mobile`, `Email`, `BirthDate`, `Pan`, `Aadhaar`, `AccountNumber`, `CounterpartyVpa`); one pure `mask(model, scopes)`; Hypothesis properties: no Role sees what its scopes do not reveal, idempotent, at most last four digits |
| Cursors | `cursors.py` | HMAC-signed `{v, k, q, sub, exp}` (LLD §5); built and tested, **not yet wired** (no paginated tool yet, no `CURSOR_KEYS` setting) |
| Runtime | `runtime.py`, `server.py` | Lifespan opens one core-api client per instance; without `INTERNAL_SIGNING_KEY` tools answer `dependency_unavailable`. Middleware order: `ErrorResults` outermost, then `Authorize` |
| Tools | `tools/customers.py`, `tools/ops.py` | `search_customers`, `get_customer_profile` with their failure matrix; `get_service_health` (needs `customers:read`) |
| Contract | `tests/test_contract.py` | Tool names, schemas and annotations snapshotted in wire form (syrupy) |

Test harness: `tests/support/gateway_harness.py` runs the gateway in-process with an injected token (`access_token(role)`) and a `FakeCoreApi` that **verifies every request's HMAC** and answers with core-api's own response models. compose now passes `CORE_API_URL` and `INTERNAL_SIGNING_KEY` to the gateway.

### Verification status

- CI green on #23: 152 gateway tests (unit and in-memory tool tests), the full existing suite, integration tests, image smoke tests. The gateway smoke test now asserts that `tools/list` works and an anonymous `tools/call` is `unauthenticated`.
- **Not yet verified:** a tool call through the gateway to a real core-api **with Postgres data** (only against the fake, and against real core-api without a database). The P3 exit criterion is "tool matrix green against compose".
- Still not verified from P1: the full 5,000-Customer `poe seed` (see Open items).

## Decisions taken in P3 so far

| Topic | Decision |
|---|---|
| Identity | One Role per principal; scopes capped by the Role; role-less principals refused (ADR 0016) |
| Tool errors | `GatewayError` subclasses FastMCP's `ToolError` (passes through unmasked); `ErrorResults` middleware renders the body as structured content and as JSON text |
| Tool inputs | Flat, annotated arguments (LLD §3 updated), strict input validation, IDs checked by pattern before any call |
| Views | Gateway-owned models with `extra="ignore"`: the gateway publishes only fields it declares |
| JWT verification | Use FastMCP's `JWTVerifier`: it already caches JWKS, refetches on an unknown `kid` and rate-limits refreshes. Configure and test it; do not hand-roll |

## Next session: P3 continued, test-first

Read first: LLD mcp-gateway §2-§7, `tests/support/gateway_harness.py`, `tests/test_customer_tools.py` (the pattern every tool module copies).

1. Branch `feat/p3-<slug>` from an up-to-date `main`.
2. **KYC tools** (`tools/kyc.py`): `get_kyc_status` (`/kyc`, PAN and Aadhaar masked via `validation_alias` from `pan_last4`/`aadhaar_last4`) and `list_kyc_documents`. **Owner to confirm first:** a proposal not yet in the LLD is to unmask the PAN only when a `kyc:pii` caller passes `reveal_pan: true` (then call `/kyc/pan`, which audits), rather than on every status check by a compliance officer. A draft test file for this design was set aside, not committed.
3. **Payments tools**: `get_account_summary`, `search_transactions` (wire `Cursors` with a `CURSOR_KEYS` setting; cursor binds the filters), `get_transaction`, `get_spending_insights`. Then risk (`list_aml_alerts`, `get_aml_alert`), knowledge (`search_knowledge_base`, `get_document`), writes (`raise_dispute`, `flag_transaction_for_review` with required `idempotency_key` and elicitation or `confirm: true`). `screen_entity` waits for P4's screening client.
4. **PII guard test**: every field on every tool output whose name suggests personal data (`mobile`, `email`, `date_of_birth`, `pan`, `aadhaar`, `account_number`, `*_vpa`) carries a masking rule.
5. **HTTP authentication**: `JWTVerifier` plus RFC 9728 metadata (`RemoteAuthProvider`), `401` with `WWW-Authenticate`; tests mint tokens with FastMCP's `RSAKeyPair` (wrong `aud`, expired, unknown `kid` triggers one refetch). Update the CI smoke test to expect `401`.
6. **Rate limits** (layers 3-5, DynamoDB via LocalStack, fail soft), **load shedding**, **audit middleware** (mints `audit_id`, posts `/v1/audit`, never fails the call; `pii_unmasked` when `/kyc/pan` was called).
7. **Against real data**: move core-api's `api_database_url`/`committed` fixtures to `tests/support`, and add gateway integration tests (CI runs them; Docker is stopped locally).

## Open items

- **Full seed:** stopped at about 600 Customers on 2026-11-14 to free memory. Before retrying: free C: to at least 10 GB (12 GB free on 2026-11-21) and agree a time when Docker can have the memory (0.8 GB RAM free on 2026-11-21); `docker compose down -v && docker compose up -d db`, then `uv run poe seed` (about 1.5 hours). Then record the counts here and in the README, and merge release PR #3.
- **Seeding RDS (P6):** PANs sealed by the local keyring cannot be opened by KMS; seal under KMS when seeding a deployed database. The master user also needs `SET` on `session_replication_role`, or the load runs with triggers on.
- KB ingestion (P5) needs a write role with `INSERT`/`UPDATE` policies on `kb.*`; `/v1/kb/search` then adds vector hits and RRF and reports `retrieval: "hybrid"`.
- A scheduled job must call `kosha.create_transaction_partitions()` to keep 3 months ahead, and can run `kosha_datagen.reconcile` (P6).
- Cognito access tokens carry `client_id`, not `aud`, unless resource binding is used; settle the audience check when wiring `JWTVerifier` (P3) and Cognito (P6).

## Suggested opening prompt for the next session

> Continue LedgerLens: P3 continued per HANDOFF.md, starting with the KYC tools.
