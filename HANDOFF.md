# Handoff

> Read at the start of every session; rewrite at the end of every session. Durable lessons go to [MEMORY.md](MEMORY.md), standing rules to [CLAUDE.md](CLAUDE.md).

**Last updated:** 2026-11-12 · **Current release:** v0.2.0 · **Phase in progress:** P1 (P1a, P1b done) · **Next:** P1c

## Where things stand

- P1 lands as three PRs: **P1a** `kosha-domain` (done), **P1b** schema and migrations (done), **P1c** generator and `poe seed`. Exit criteria (plan §9): `uv run poe seed` loads the full dataset; the ledger reconciles.
- `core-api` owns six Alembic revisions under `services/core-api/src/core_api/migrations/versions/`, raw SQL with enum labels frozen as literals:

| Rev | Adds |
|---|---|
| 0001 | `vector`, `pg_trgm`; schemas `kosha core ledger kyc risk ops kb`; `kosha_app` role (NOLOGIN); `kosha.is_id()` |
| 0002 | core + ledger tables; `core.transactions` monthly partitions (18 back, 3 ahead, default) via `kosha.create_transaction_partitions()` |
| 0003 | KYC, risk, ops tables; `kosha.forbid_change()`; append-only audit log |
| 0004 | `kb.documents`, `kb.chunks`; RLS ceiling on **both** via `kb.caller_ceiling()` |
| 0005 | `kosha.allowed_transitions` (127 edges) + `*_lifecycle` triggers on 8 status columns |
| 0006 | deferred zero-sum triggers on postings **and** journal entries; ledger and history append-only |

- 180 integration tests (`uv run poe test-integration`) run against the pgvector image read from `compose.yaml`. Parity tests fail if a DB enum or transition drifts from `kosha-domain`. Shared row helpers: `services/core-api/tests/support/db_rows.py` (on pytest's `pythonpath`).
- `uv run poe migrate` upgrades `$DATABASE_URL` (default: the compose DB on 55432). Verified against the compose stack; it is idempotent.
- CI has a new **Integration tests** job. ADR 0011 records composite FKs to partitioned transactions.

## Decisions taken this session (beyond the LLD, all reflected in the LLD now)

| Topic | Decision |
|---|---|
| Postings | `gl_account` enum + `account_id` set **only** for `customer_deposits` (CHECK). Internal GLs: per-rail settlement, `fee_income`, `gst_payable`, `interest_expense`, `suspense`. |
| UTR | Plain partial index, **not unique**: a unique index must include `initiated_at`, and on-us transfers share a UTR. |
| Balances | `available_balance_paise` is a generated column (ledger − hold). |
| Composite FKs | Also pin transaction→account owner, KYC document→profile customer, alert→rule typology, chunk→document classification (`ON UPDATE CASCADE`). |
| Lifecycle trigger | UPDATE only; inserts take any status. Raises `check_violation`, constraint `*_lifecycle`, message identical to `IllegalTransitionError`. |
| Vocabulary | Actor `staff` (not `ops_user`), dispute reason `unauthorised`, product codes `fixed_deposit`/`recurring_deposit`. |

## Next session: P1c — generator and `poe seed`

1. Branch `feat/p1-generator` from an up-to-date `main`.
2. Read first: plan v0.2 §0 (realism rules), §1a (status distributions), §2 (volumes); data-model LLD §§2-3, 8; core-api LLD §5 (posting table). Read the six revisions: they are the contract the generator writes to.
3. Create `packages/kosha-datagen` (plan v1.0 §7). Pure row streams first (seam 3), then a loader that `COPY`s them (seam 4). Curated Indian name/city lists, not Faker; full volume by default, `--scale` for tests.
4. **Load as the table owner, not `kosha_app`:** `kosha_app` cannot write `kb.*` (RLS has no write policy) and P1c does not need to.
5. **Commit in batches.** Deferred balance triggers queue one event per posting until commit; one 3M-posting transaction risks the 3 GB Docker cap. Write each transaction's status history alongside it (inserts skip lifecycle checks; history is the generator's job).
6. **Partitions:** anchor the dataset so `initiated_at` falls inside the migrated window, or call `kosha.create_transaction_partitions()` for the seed's range **before** loading; rows already in the default partition block creating that month later.
7. Add a reconciliation query (cached `ledger_balance_paise` = Σ postings per account, via `postings_account_idx`) and make it the seed's exit check; consider shipping it as a view in revision 0007.
8. `poe seed` = migrate + generate + load + reconcile.

## Open items

- **Owner action:** after this PR's first CI run, add "Integration tests" to the *Protect main* ruleset's required checks.
- KB ingestion (P5) needs a write path: a dedicated role with `INSERT`/`UPDATE` policies on `kb.*`, since `FORCE` RLS binds the owner too.
- core-api's error mapping (P2) should turn `check_violation` with constraint `*_lifecycle` into 409 `conflict`, and `restrict_violation` (append-only) into 409 as well.
- A scheduled job must call `kosha.create_transaction_partitions()` to keep 3 months ahead (P6).
- Docker on this machine is capped at 3 GB (`~/.wslconfig`); run one testcontainers Postgres at a time. The first testcontainers run on a machine pulls Ryuk and pgvector and may time out once.

## Suggested opening prompt for the next session

> Continue LedgerLens: start P1c per HANDOFF.md.
