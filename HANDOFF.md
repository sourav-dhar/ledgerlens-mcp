# Handoff

> Read at the start of every session; rewrite at the end of every session. Durable lessons go to [MEMORY.md](MEMORY.md), standing rules to [CLAUDE.md](CLAUDE.md).

**Last updated:** 2026-11-12 · **Current release:** v0.2.0 · **Phase in progress:** P1 (P1a done) · **Next:** P1b

## Where things stand

- P1 lands as three PRs: **P1a** `kosha-domain` (done), **P1b** schema and migrations, **P1c** generator and `poe seed`. Exit criteria (plan §9): `uv run poe seed` loads the full dataset; the ledger reconciles.
- `packages/kosha-domain` provides `Paise` and rupee formatting, prefixed ULIDs (seeded clock + RNG), the eight status lifecycles, `IndianState` with GST codes and pincode resolution, validators (PAN, IFSC, VPA, RRN, UTR, GSTIN checksum, mobile) and `Rail`. 100% covered, pyright strict clean.
- Lifecycle tests parse the Mermaid state diagrams in `docs/architecture/lld/data-model.md`: changing a lifecycle means changing the diagram in the same commit.

## Decisions taken with the owner this session (apply in P1b/P1c)

| Topic | Decision |
|---|---|
| Test seams | (1) `kosha_domain` public API; (2) migrated DB via testcontainers; (3) generator row streams, pure; (4) seed end to end with reconciliation. Tests only at these seams. |
| Partitioned `core.transactions` | PK `(txn_id, initiated_at)`; child tables (status history, journal entries, disputes, reviews) carry `txn_initiated_at` and use a **composite FK**. Record as an ADR and update the LLD in P1b. |
| Integration tests in CI | New **required** "Integration tests" job. The owner adds it to the *Protect main* ruleset after it first runs. |
| Migrations | Raw SQL via `op.execute`, no ORM models. Enum values are frozen as literals in each migration (not imported from `kosha-domain`); a parity test fails if DB and domain drift. |
| Generator | Curated Indian name/city lists, not Faker (Faker output is not stable across versions, which would break `--seed`). Full volume by default, `--scale` for tests; rows are streamed into `COPY`, never held in memory. |

## Next session: P1b — schema and migrations

1. Branch `feat/p1-schema` from an up-to-date `main`.
2. Read first: `docs/plans/v0.2-data-model-and-corpus.md` §1, `docs/architecture/lld/data-model.md` §§1-7, `docs/architecture/lld/core-api.md` (psycopg 3 pool, `migrations/` location).
3. Add the remaining vocabulary enums to `kosha_domain.vocabulary` (persona, segment, product code, txn type, channel, direction, …) as the schema needs them.
4. `core-api` gains `alembic`, `psycopg[binary]` and depends on `kosha-domain`; dev group gains `testcontainers[postgres]`.
5. Migrations, test-first against testcontainers `pgvector/pgvector` (same digest as `compose.yaml`): schemas `core ledger kyc risk ops kb kosha`; enum types; `kosha.allowed_transitions` filled from the lifecycles + a trigger per status column (illegal transition raises); monthly transaction partitions 18 months back and 3 ahead plus a default partition; deferred zero-sum constraint trigger on `ledger.postings`; `ops.audit_log` with UPDATE/DELETE revoked; RLS on `kb.chunks` with `FORCE`; indexes from LLD §6.
6. **Dockerfile trap:** once `core-api` depends on `kosha-domain`, copy `packages/` in the builder **and** runtime stages, and change the `dist_info="$(echo /app/.venv/.../kosha_*.dist-info)"` step: it will match two directories (`kosha_core_api`, `kosha_domain`) and the `rm`/`sed` will break. Loop over the matches instead.
7. Add the CI integration job (Docker is available on `ubuntu-24.04` runners) and the ADR for composite FKs.

## Open items

- Owner action after P1b's first CI run: add "Integration tests" to the ruleset's required checks.
- Docker on this machine is capped at 3 GB (`~/.wslconfig`); run one testcontainers Postgres at a time.
- Possible follow-ups in MEMORY.md "Deferred": distroless runtime image, image signing, MkDocs Material → Zensical.

## Suggested opening prompt for the next session

> Continue LedgerLens: start P1b per HANDOFF.md.
