# Handoff

> Read at the start of every session; rewrite at the end of every session. Durable lessons go to [MEMORY.md](MEMORY.md), standing rules to [CLAUDE.md](CLAUDE.md).

**Last updated:** 2026-11-17 · **Current release:** v0.2.0 (v0.3.0 pending in #3) · **Phase complete:** P2 Core Banking API · **Next:** P3 MCP gateway

## Where things stand

- **P2 is complete** (plan §9 exit: "All routes + failure tests green"). `core-api` serves 16 routes, all behind gateway-signed requests ([ADR 0013](docs/adr/0013-gateway-signs-internal-requests-with-hmac.md)). The [core-api LLD §8](docs/architecture/lld/core-api.md#8-failure-matrix) maps each row of the plan §8 failure matrix to where `core-api` tests it, or to the phase that owns it.

  | Area | Routes | PR |
  |---|---|---|
  | Foundation | units of work as `kosha_app`, error mapping, `/readyz` at Alembic head | #9 |
  | Internal auth | HMAC-signed principal headers, fail closed | #10 |
  | Customers, KYC | `/v1/customers`, `/{id}`, `/{id}/kyc`, `/kyc/documents`, `/kyc/pan` | #9, #13, #18 |
  | Accounts, payments | `/v1/accounts/{id}`, `/transactions` (keyset), `/insights` (Kolkata months), `/v1/transactions/{id}` | #11, #15 |
  | Risk | `/v1/aml/alerts` (SLA queue), `/{id}` (rule + evidence) | #15 |
  | Writes | `POST /v1/disputes`, `POST /v1/reviews`: idempotency + row lock + outbox in one transaction (ADR 0007, 0008) | #14 |
  | Knowledge, audit | `/v1/kb/search` (full text until P5), `/v1/kb/documents/{code}`, `POST /v1/audit` | #17 |

- **PAN unmasking** ([ADR 0014](docs/adr/0014-pan-envelope-encryption-behind-a-keyring.md)): `kosha_domain.vault` seals each PAN with its own data key, wrapped by a `Keyring` and bound to the Customer. `LocalKeyring` stands in for KMS until P6. The generator seals real synthetic PANs, and `/kyc/pan` audits every unmasking in the same transaction.
- **Guards that cover future routes automatically:** `tests/test_route_guards.py` reads the OpenAPI document and requires every `/v1` route to answer `401` unsigned and `503` without a database. `tests/test_contract.py` snapshots the whole contract.
- **CI coverage** now combines unit and integration data before the 90% gate (99% at P2's close); `Tests & coverage` waits for `Integration tests`.

### Verification status

- Verified in CI on every PR: 536 unit tests, the integration suite (every route, both write races, RLS ceilings, PAN round trip) and the image smoke test.
- **Still not verified: the full 5,000-Customer `poe seed`** (see Open items). Integration tests have run only in CI since 2026-11-14, because Docker Desktop is kept stopped to free memory.

## Decisions taken in P2

| Topic | Decision |
|---|---|
| Internal authentication | HMAC over timestamp, method, target, actor, ceiling and body hash; ±60 s; keys `new,old` (ADR 0013) |
| PANs | Envelope encryption behind a keyring; local keyring until KMS (ADR 0014) |
| Least privilege | Every unit of work `SET`s role `kosha_app`; KB ceilings are enforced only by RLS |
| Errors | One body; lifecycle and append-only refusals `409`, pool and connection `503` + `Retry-After`, statement timeout `504` |
| Paging | Keyset with `limit + 1`; Transactions by `(initiated_at, txn_id)` desc in a half-open window ≤ 366 days; alerts by `(sla_due_at, alert_id)` |
| Disputes | Debits that moved money; amount ≤ the Transaction's; one open dispute; RBI turnaround in `kosha_domain.disputes` |
| Insights | Kolkata calendar months, the one IST bucket in `core-api` |
| Readiness | Ready only at the shipped Alembic head; the Lambda adapter waits on `/healthz` |

## Next session: P3 MCP gateway, test-first

Read first: the [mcp-gateway LLD](docs/architecture/lld/mcp-gateway.md) (whole), plan v1.0 §4 (tools, scopes and roles) and §8, ADRs 0001, 0004, 0006 and 0013, and the core-api LLD §7–8 (the contract and failure matrix the client must handle).

1. Branch `feat/p3-<slug>` from an up-to-date `main`.
2. **`clients/core_api.py`**: a typed httpx client whose auth flow signs the final encoded URL with `kosha_domain.signing.sign` (see `tests/support/signed.py`), mapping `core-api`'s error codes to the gateway taxonomy.
3. **`auth/`**: Principal, scopes and the role table from plan §4; `kyc:pii` decides between `/kyc` (masked) and `/kyc/pan`.
4. **`masking.py`** (pure) and **`cursors.py`** (HMAC-signed keyset positions, LLD §5).
5. **Tools**, one module at a time, through FastMCP's in-memory `Client` against a real `core-api` app, each with its failure matrix.
6. The audit middleware posts to `/v1/audit` and never fails the call.

## Open items

- **Full seed:** stopped at about 600 Customers on 2026-11-14 to free memory; C: then had 7 GB free. Before retrying: free C: to at least 10 GB and agree a time when Docker can have the memory; `docker compose down -v && docker compose up -d db`, then `uv run poe seed` (about 1.5 hours). Then record the counts here and in the README, and merge release PR #3 (it will now carry P2 too).
- **Seeding RDS (P6):** PANs sealed by the local keyring cannot be opened by KMS; seal under KMS when seeding a deployed database. The master user also needs `SET` on `session_replication_role`, or the load runs with triggers on.
- KB ingestion (P5) needs a write role with `INSERT`/`UPDATE` policies on `kb.*`; `/v1/kb/search` then adds vector hits and RRF and reports `retrieval: "hybrid"`.
- A scheduled job must call `kosha.create_transaction_partitions()` to keep 3 months ahead, and can run `kosha_datagen.reconcile` (P6).

## Suggested opening prompt for the next session

> Continue LedgerLens: start P3 (MCP gateway) per HANDOFF.md.
