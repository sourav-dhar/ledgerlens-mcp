# Handoff

> Read at the start of every session; rewrite at the end of every session. Durable lessons go to [MEMORY.md](MEMORY.md), standing rules to [CLAUDE.md](CLAUDE.md).

**Last updated:** 2026-11-13 · **Current release:** v0.2.0 · **Phase in progress:** P1 (P1c in review) · **Next:** verify the full seed, merge, release v0.3.0, then P2

## Where things stand

- **P1c is built and in review** (PR from `feat/p1-generator`): `kosha-datagen` and `uv run poe seed`. The exit criterion is **not yet verified at full volume**; see below.
- `packages/kosha-datagen` (design: [LLD](docs/architecture/lld/datagen.md)) is a pure row-stream generator (`generate(config)`, seam 3) plus a `COPY` loader and `reconcile` (seam 4). A dataset is fixed by `(seed, as_of, scale)`; a smaller scale is an exact prefix of a larger one.
- Revision **0007** adds the `opening_balances` GL account ([ADR 0012](docs/adr/0012-opening-balances-gl-for-balances-brought-forward.md)) and the `ledger.account_reconciliation` view.
- Shared test support moved to `tests/support/`: `pg_container.py` (one Postgres container per session, loaded as a plugin from the root `conftest.py`) and `db_rows.py`.

### Verification status

- Verified: 60 datagen tests. The row-stream tests check formats, lifecycles, balanced entries, cached balance = Σ Postings, distributions and every typology at 150–375 Customers. The integration tests load into a migrated pgvector database, cover partitions and the CLI end to end, and prove that `reconcile` finds orphans and unbalanced entries.
- Benchmarked: 200 Customers load in 32 s with triggers off, against 145 s or more with them on.
- **Not verified: the full 5,000-Customer `poe seed`.** The first attempt crashed Postgres when C: filled up (99% full). The second reached about 1,600 Customers before the machine or Docker stopped. It was I/O-bound on Docker Desktop's virtual disk and slowing (about 40 Customers a minute), so expect 1.5–2 hours here.

## Decisions taken this session

| Topic | Decision |
|---|---|
| Opening balances | Accounts older than the window start with a no-Transaction entry against `opening_balances` (ADR 0012), chosen over `suspense` and over window-only Accounts |
| Money that comes back | A reversal or refund is its own credit Transaction: a journal entry belongs to exactly one Transaction (`UNIQUE (txn_id, txn_initiated_at)`) |
| Outcomes | Explicit scenario paths per Rail (`outcomes.py`), cut at the as-of date, so open cases exist only on recent Transactions |
| Bad actors | Index ≡ 16 (mod 50), typologies in rotation: exactly 2%, every typology present from 350 Customers |
| AML alerts | Detected by seven rules over posted Transactions (thresholds in `risk.aml_rules.params`), never planted; loan-funded down payments supply most false positives |
| Bulk load | `COPY` with `session_replication_role = replica` (11× faster); `reconcile` proves every foreign key, balanced entries, cached balances and a zero-sum ledger set-based. Roles without the `SET` privilege load with triggers on |

## Next session: finish P1, then P2

1. Start Docker Desktop, run `docker compose down -v && docker compose up -d db`, then run `uv run poe seed` and leave it to finish (keep 10 GB free on C:). To speed it up, consider raising `shared_buffers` and `max_wal_size` for the compose `db` service: the load waits on data-file I/O.
2. Record the printed row counts here and in the README progress row, merge the P1c PR once CI is green, then merge the release-please PR for **v0.3.0**.

### P2: Core Banking API, test-first

1. Branch `feat/p2-<slug>` from an up-to-date `main`.
2. Read first: core-api LLD (whole), plan v1.0 §§3–5 and §8 (failure matrix), ADRs 0001, 0007, 0008, 0011.
3. Build the `db/` layer (pool, unit of work, RLS context) and repositories against the seeded schema; `poe seed --scale 0.02` gives a realistic local database in under a minute.
4. Map database errors: `check_violation` with constraint `*_lifecycle` → 409 `conflict`; `restrict_violation` (append-only) → 409.
5. Routes per the LLD, each with its failure tests; contract-snapshot the OpenAPI document (`syrupy`).

## Open items

- **Owner action:** add "Integration tests" to the *Protect main* ruleset's required checks (carried over from P1b).
- **Disk:** C: was 99% full and crashed the first full seed. A full dataset needs about 5 GB of Postgres data and WAL; keep 10 GB free, and `docker builder prune` periodically.
- KB ingestion (P5) needs a write path: a dedicated role with `INSERT`/`UPDATE` policies on `kb.*`, since `FORCE` RLS binds the owner too.
- A scheduled job must call `kosha.create_transaction_partitions()` to keep 3 months ahead (P6). The same job can run `kosha_datagen.reconcile` against production-shaped data.
- Seeding RDS (P6): the master user is not a superuser; grant `SET` on `session_replication_role` or accept a slower trigger-on load.
- Volumes are close to plan v0.2 §2 but not equal (cards ≈ 0.95 per Customer against ≈ 1.2 planned); the plan marks them "proposed".

## Suggested opening prompt for the next session

> Continue LedgerLens: verify the full seed and merge P1c per HANDOFF.md, then start P2.
