# Handoff

> Read at the start of every session; rewrite at the end of every session. Durable lessons go to [MEMORY.md](MEMORY.md), standing rules to [CLAUDE.md](CLAUDE.md).

**Last updated:** 2026-11-27 · **Current release:** v0.2.0 (v0.3.0 pending in #3) · **Phase in progress:** P3 MCP gateway: foundation (#23), real-data tests and KYC (#28), payments tools (#30), AML-alert tools (#31), knowledge tools (#32), write tools (#33) · **Next:** PII guard test, JWT, rate limits and audit

## Where things stand

P2 is complete (see the core-api LLD §8 failure matrix). P3's foundation landed in #23. Every tool built on it follows LLD §3, and its pieces are:

| Piece | Module | What it guarantees |
|---|---|---|
| Error taxonomy | `errors.py` | Every failure is an `isError` result with `{"error": {code, message, trace_id, retry_after_s?, dependency?}}`; validation errors name the field without echoing the value; anything unexpected is `internal` with only a trace ID |
| core-api client | `clients/core_api.py` | Signs the final encoded target per attempt (ADR 0013); maps core-api codes to the taxonomy (`401` from core-api is `internal`: a key mismatch); retries connect errors, timeouts, `503`, `504` once, writes only with their original `Idempotency-Key` |
| Principal | `auth/principal.py`, `auth/scopes.py` | Exactly one Role per principal (Cognito group, or `MACHINE_CLIENT_ROLES` for service clients); scopes = token ∩ Role ([ADR 0016](docs/adr/0016-one-role-per-principal-scopes-capped-by-role.md)); KB ceiling sent only with `kb:read`. The role table is tested against plan v1.0 §4 |
| Authorization | `middleware/authorize.py` | Stage 4: principal resolved once per call; scope from `TOOL_SCOPES` (all 16 tools, tested against LLD §6); an unlisted tool is refused; no identity is `unauthenticated` |
| Masking | `masking.py` | Rules declared on field types (`Mobile`, `Email`, `BirthDate`, `Pan`, `Aadhaar`, `AccountNumber`, `CounterpartyVpa`, `OwnVpa`; `Withheld` via `AML_ONLY` for device and location); one pure `mask(model, scopes)`; Hypothesis properties: no Role sees what its scopes do not reveal, idempotent, at most last four digits |
| Cursors | `cursors.py` | HMAC-signed `{v, k, q, sub, exp}` (LLD §5), wired with `CURSOR_KEYS`; `search_transactions` and `list_aml_alerts` bind their filters (lists sorted, `limit` excluded) and the caller, so a cursor cannot cross searches |
| Runtime | `runtime.py`, `server.py` | Lifespan opens one core-api client per instance; without `INTERNAL_SIGNING_KEY` tools answer `dependency_unavailable`. Middleware order: `ErrorResults` outermost, then `Authorize` |
| Tools | `tools/customers.py`, `tools/kyc.py`, `tools/payments.py`, `tools/risk.py`, `tools/knowledge.py`, `tools/writes.py`, `tools/ops.py` | `search_customers`, `get_customer_profile`, `get_kyc_status`, `list_kyc_documents`, `get_account_summary`, `search_transactions`, `get_transaction`, `get_spending_insights`, `list_aml_alerts` (soonest SLA first), `get_aml_alert` (rule thresholds and triggering Transactions in the payments view), `search_knowledge_base` and `get_document` (the Role's KB ceiling enforced by row-level security; reference-only `notice`; at most 12 KB per result, with `omitted` and `next_chunk`), `raise_dispute` and `flag_transaction_for_review` (required `idempotency_key`, `replayed` on a retry) with their failure matrix; amounts carry `*_display` strings; `get_service_health` (needs `customers:read`). The full PAN only via `reveal_pan: true` with `kyc:pii` (owner's decision, LLD §6) |
| Write confirmation | `confirmation.py` | The user agrees to every write: `input_required` on 2026-07-28 connections, `elicitation/create` before, `confirm: true` only for clients that cannot ask (ignored when they can); no/decline/dismiss is `declined` ([ADR 0017](docs/adr/0017-writes-confirmed-by-elicitation-in-either-protocol-era.md)) |
| Contract | `tests/test_contract.py` | Tool names, schemas and annotations snapshotted in wire form (syrupy); `ErrorCode` held to LLD §4 by `tests/test_errors.py` |

Test harness: `tests/support/gateway_harness.py` runs the gateway in-process with an injected token (`access_token(role)`) and a `FakeCoreApi` that **verifies every request's HMAC** and answers with core-api's own response models. `tests/support/api_database.py` (moved from core-api) gives every suite the committed scratch database; `services/mcp-gateway/tests/integration/` runs tools through real core-api on it (its `conftest.py` provides `core_api_app`). compose passes `CORE_API_URL` and `INTERNAL_SIGNING_KEY` to the gateway.

### Verification status

- 320 gateway unit and tool tests; the image smoke test asserts that `tools/list` works and an anonymous `tools/call` is `unauthenticated`.
- **Real data, verified locally on 2026-11-25 and in CI:** 19 gateway integration tests run every tool module through real core-api on Postgres, including a real PAN reveal that leaves exactly one audit record, a transaction search and an alert queue each paged to the last row through real cursors, a confidential Document an analyst reads but a support agent cannot find, and a retried dispute written once with one outbox event. Every new tool module adds its own end-to-end file the same way.
- The P3 exit criterion, "tool matrix green against compose", still needs the remaining tools and a run against the compose stack itself.
- Still not verified from P1: the full 5,000-Customer `poe seed` (see Open items).

## Decisions taken in P3 so far

| Topic | Decision |
|---|---|
| Identity | One Role per principal; scopes capped by the Role; role-less principals refused (ADR 0016) |
| Tool errors | `GatewayError` subclasses FastMCP's `ToolError` (passes through unmasked); `ErrorResults` middleware renders the body as structured content and as JSON text |
| Tool inputs | Flat, annotated arguments (LLD §3 updated), strict input validation, IDs checked by pattern before any call |
| Views | Gateway-owned models with `extra="ignore"`: the gateway publishes only fields it declares |
| Own VPAs, device detail | A Customer's own VPA is masked like the mobile (it often is the mobile); a Transaction's device ID, IP and coordinates are withheld without `aml:read` (LLD §7) |
| PAN unmasking | Only on request: `reveal_pan: true` with `kyc:pii` calls the audited `/kyc/pan`; a status check never unmasks (owner, 2026-11-25) |
| Write confirmation | Elicitation in either protocol era; `confirm: true` only where the client cannot ask; over the deployed stateless transport 2025-era clients confirm with `confirm` (ADR 0017) |
| KB result size | At most 12 KB of encoded JSON per knowledge result: a search drops its lowest-ranked passages (`omitted`); a Document is read in windows (`next_chunk` is a plain chunk index, as nothing in it is sensitive); a chunk too large alone is clipped |
| JWT verification | Use FastMCP's `JWTVerifier`: it already caches JWKS, refetches on an unknown `kid` and rate-limits refreshes. Configure and test it; do not hand-roll |

## Next session: P3 continued, test-first

Read first: LLD mcp-gateway §2-§7, ADR 0015 (rate limits) and 0017 (write confirmation), `tests/support/gateway_harness.py`, `middleware/authorize.py` (the middleware pattern) and `tests/test_write_tools.py` (both protocol eras and the deployed transport, `serve_http`, in memory).

1. Branch `feat/p3-<slug>` from an up-to-date `main`.
2. 15 of 16 tools are live; `screen_entity` waits for P4's screening client.
3. **PII guard test**: every field on every tool output whose name suggests personal data (`mobile`, `email`, `date_of_birth`, `pan`, `aadhaar`, `account_number`, `*_vpa`) carries a masking rule.
4. **HTTP authentication**: `JWTVerifier` plus RFC 9728 metadata (`RemoteAuthProvider`), `401` with `WWW-Authenticate`; tests mint tokens with FastMCP's `RSAKeyPair` (wrong `aud`, expired, unknown `kid` triggers one refetch). Update the CI smoke test to expect `401`.
5. **Rate limits** (layers 3-5, DynamoDB via LocalStack, fail soft), **load shedding**, **audit middleware** (mints `audit_id`, posts `/v1/audit`, never fails the call; `pii_unmasked` when `/kyc/pan` was called).
6. **Resources and prompts** (LLD §2: `resources.py` for `kb://{department}/{doc_code}` and `customer://{customer_id}`, through the same ceiling, masking and 12 KB budget as the tools; `prompts.py`). Every tool module already has an end-to-end file; new modules follow `tests/integration/test_knowledge_end_to_end.py` (real core-api, committed rows, unique per test).

## Open items

- **Injection-suspect `warning`** on a passage (RAG LLD §4) needs ingestion's heuristic scanner (P5) and a core-api field; the gateway's reference-only `notice` and 12 KB cap are in place.
- **Full seed:** stopped at about 600 Customers on 2026-11-14 to free memory. Before retrying: free C: to at least 10 GB (6.6 GB free on 2026-11-25, down from 12 GB on 2026-11-21) and agree a time when Docker can have the memory (0.1-0.9 GB RAM free on 2026-11-25 with Docker running); `docker compose down -v && docker compose up -d db`, then `uv run poe seed` (about 1.5 hours). Then record the counts here and in the README, and merge release PR #3.
- **Seeding RDS (P6):** PANs sealed by the local keyring cannot be opened by KMS; seal under KMS when seeding a deployed database. The master user also needs `SET` on `session_replication_role`, or the load runs with triggers on.
- KB ingestion (P5) needs a write role with `INSERT`/`UPDATE` policies on `kb.*`; `/v1/kb/search` then adds vector hits and RRF and reports `retrieval: "hybrid"`.
- A scheduled job must call `kosha.create_transaction_partitions()` to keep 3 months ahead, and can run `kosha_datagen.reconcile` (P6).
- Cognito access tokens carry `client_id`, not `aud`, unless resource binding is used; settle the audience check when wiring `JWTVerifier` (P3) and Cognito (P6).

## Suggested opening prompt for the next session

> Continue LedgerLens: P3 continued per HANDOFF.md, starting with the PII guard test and JWT authentication.
