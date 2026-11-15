# Handoff

> Read at the start of every session; rewrite at the end of every session. Durable lessons go to [MEMORY.md](MEMORY.md), standing rules to [CLAUDE.md](CLAUDE.md).

**Last updated:** 2026-11-15 · **Current release:** v0.2.0 (v0.3.0 pending in #3) · **Phase in progress:** P2 Core Banking API · **Next:** KB search, audit log, PAN unmasking; then the P2 exit check

## Where things stand

- **P2 is under way, test-first, one slice per pull request.** On `main`:

  | PR | Slice |
  |---|---|
  | #9 | `core_api.db` (pool + `unit_of_work`), error mapping, `/readyz` at the shipped Alembic head, `GET /v1/customers` and `/v1/customers/{id}` |
  | #10 | Gateway-signed internal requests ([ADR 0013](docs/adr/0013-gateway-signs-internal-requests-with-hmac.md)): `kosha_domain.signing`, `401 unauthenticated`, fail closed without `INTERNAL_SIGNING_KEYS` |
  | #11 | `GET /v1/accounts/{id}`, keyset-paged `GET /v1/accounts/{id}/transactions`, `GET /v1/transactions/{id}` with status history |
  | #13 | `GET /v1/customers/{id}/kyc` (newest profile + events; PAN and Aadhaar as last 4 only) and `.../kyc/documents` (metadata only) |
  | #14 | `POST /v1/disputes`, `POST /v1/reviews`: idempotency key → `FOR UPDATE` lock → rules → case row + outbox event → stored response, one transaction (`services/idempotency.py`, `services/cases.py`); dispute rules in `kosha_domain.disputes` |
  | #15 | `GET /v1/aml/alerts` (SLA queue, keyset on `(sla_due_at, alert_id)`), `GET /v1/aml/alerts/{id}` (rule + cited Transactions), `GET /v1/accounts/{id}/insights` (Kolkata months, posted only, by category) |

- **How a write is built:** `CaseService` wraps its work in `idempotent(...)`; refusals raise `ApiError`s inside the unit of work so the key rolls back too. Replays answer `200`, first writes `201`.
- **How a read is built** (copy this shape): validate IDs with `deps.checked_id` and cross-field rules in the handler (`400`), then `require(database).unit_of_work(caller, read_only=True)`, one repository call, `404` on `None`. SQL lives only in `repositories/`, response models in `schemas/`. Unit tests (`tests/test_*_routes.py`) cover validation against an app with no database (valid input answers `503`); integration tests (`tests/integration/test_*_api.py`) commit rows to the scratch database `kosha_api_test` and call the app through `SignedAs`.
- **Every unit of work** runs as `kosha_app` with `transaction_read_only`, `statement_timeout`, `kosha.actor` and `kosha.kb_ceiling` set in one `set_config` round trip; all transaction-local.
- **Contract:** `tests/test_contract.py` snapshots the OpenAPI document (`syrupy`). A route change is an intended snapshot diff: run with `--snapshot-update`, then convert the file to LF (syrupy writes CRLF on Windows).
- `/readyz` is `503` until the database is at Alembic head; the Lambda Web Adapter waits on `/healthz` instead.

### Verification status

- Verified in CI (all 10 checks on each PR): 468 unit tests, the integration suite (database layer, every route, both write races) and the image smoke test.
- **Not verified locally this session:** the integration tests. Docker Desktop was stopped to free memory, so CI was their only run.
- **Still not verified: the full 5,000-Customer `poe seed`** (see Open items).

## Decisions taken this session

| Topic | Decision |
|---|---|
| Internal authentication | HMAC-SHA256 over timestamp, method, target, actor, ceiling and body hash; ±60 s; keys `new,old` during rotation; fail closed (ADR 0013) |
| Least privilege | Every unit of work `SET`s role `kosha_app`, so grants, append-only triggers and RLS bind even a superuser login |
| Readiness | Ready only at the shipped Alembic head; the Lambda adapter probes liveness so a database outage cannot block cold starts |
| Errors | One body `{"error": {"code", "message"}}`; lifecycle and append-only refusals are `409`, pool and connection failures `503` with `Retry-After`, statement timeouts `504`, anything else `500` |
| Paging | Keyset `(initiated_at, txn_id)` descending, `limit + 1` instead of `count(*)`, half-open window defaulting to 90 days and capped at 366 |
| Database availability | Checked inside the handler (`require`), because a raising dependency would pre-empt FastAPI's `422`/`400` validation |
| Disputes | Debits that moved money only; amount ≤ the Transaction's; one open dispute per Transaction; `tat_due_at` from RBI turnaround (T+1, T+5 for ATM and cards) |
| Insights months | Kolkata calendar months, the one deliberate IST bucket in `core-api`; storage stays UTC |

## Next session: finish P2

1. **KB search** (`/v1/kb/search`, `/v1/kb/documents/{doc_code}`): read `docs/architecture/lld/rag-pipeline.md` first. The ceiling RLS on `kb.*` already works through `kosha.kb_ceiling`; P2 needs full-text search over `kb.chunks`, with vector search and RRF following in P5 once ingestion exists.
2. **Audit** (`POST /v1/audit`): its own short transaction, never joined with business writes (LLD §3); `ops.audit_log` is append-only.
3. **PAN unmasking** for `kyc:pii`: decide how the KMS decrypt is faked locally (likely a local key behind an interface, real KMS in P6), probably as an ADR.
4. **P2 exit check** (plan §9: "All routes + failure tests green"): walk the plan §8 failure matrix against each route and fill any gaps, then close P2 in the README and plan.

## Open items

- **Full seed:** stopped at about 600 Customers on 2026-11-14 because Docker's memory was needed elsewhere. C: then had 7 GB free: it fell from 22 GB in ten minutes while Postgres used 1.4 GB, so something outside this repo was writing to it. Before the next attempt: free C: to at least 10 GB, start Docker, `docker compose down -v && docker compose up -d db`, `uv run poe seed` (about 1.5 hours at about 57 Customers a minute). Then record the counts here and in the README, and merge release PR #3.
- **The gateway does not sign yet.** `kosha_domain.signing.sign` and `tests/support/signed.py` show how; P3's httpx client needs an auth flow that signs the final encoded URL.
- KB ingestion (P5) needs a write path: a dedicated role with `INSERT`/`UPDATE` policies on `kb.*`, since `FORCE` RLS binds the owner too.
- A scheduled job must call `kosha.create_transaction_partitions()` to keep 3 months ahead (P6); the same job can run `kosha_datagen.reconcile`.
- Seeding RDS (P6): the master user is not a superuser; grant `SET` on `session_replication_role` or accept a slower trigger-on load.

## Suggested opening prompt for the next session

> Continue LedgerLens P2 per HANDOFF.md: KB search, audit, PAN unmasking, then the P2 exit check.
