# Handoff

> Read at the start of every session; rewrite at the end of every session. Durable lessons go to [MEMORY.md](MEMORY.md), standing rules to [CLAUDE.md](CLAUDE.md).

**Last updated:** 2026-11-12 · **Current release:** v0.2.0 · **Phase just finished:** P0 · **Next phase:** P1

## Where things stand

- P0 is complete and released as [v0.2.0](https://github.com/sourav-dhar/ledgerlens-mcp/releases/tag/v0.2.0): uv workspace with three walking-skeleton services, hardened Docker image, compose stack, CI/CD, docs site, HLD/LLD, ADRs, glossary.
- `main` is protected by the **Protect main** ruleset: changes land only through pull requests with all 8 CI checks green, squash or rebase merge, linear history, no force-push, Trivy HIGH+ blocks merging.
- Releases are automated: release-please keeps a release PR open; merging it tags and publishes.

## Next session: P1 — synthetic data and schema

Exit criteria (plan §9): `uv run poe seed` loads the full dataset; the ledger reconciles.

1. Branch: `git switch -c feat/p1-data-and-schema` from an up-to-date `main`.
2. Read first: `docs/plans/v0.2-data-model-and-corpus.md` (schemas, §1a status lifecycles, volumes), `docs/architecture/lld/data-model.md`, `GLOSSARY.md`.
3. Build test-first (`tdd` skill), in this order:
   1. `packages/kosha-domain`: `Paise` money type, prefixed ULIDs, status enums and transition tables, validators (PAN, IFSC, UPI VPA, UTR/RRN, GSTIN, Indian mobile, pincode).
   2. Alembic migrations in `services/core-api` for every v0.2 schema, including transaction partitioning, the ledger zero-sum constraint and row-level security on `kb.chunks`.
   3. `packages/kosha-datagen`: seeded deterministic generator (personas, salary and EMI cycles, festive spikes, planted AML typologies), bulk-loaded with `COPY`.
   4. Integration tests on testcontainers Postgres + pgvector; ledger reconciliation test.
   5. `seed` poe task wired to the compose database.
4. Adding `packages/*` touches the Dockerfile (copy package source in builder **and** runtime stages), `[tool.uv.workspace].members`, pyright/coverage/pytest paths in `pyproject.toml`.
5. Close the phase: update README "Build progress", rewrite this file, append to MEMORY.md, open the PR, wait for green CI, rebase-merge, then merge the release PR.

## Open items

- Docker on this machine is capped at 3 GB (`~/.wslconfig`); run heavy containers one at a time and stop them when done.
- Possible follow-ups recorded in MEMORY.md "Deferred": distroless runtime image, image signing, MkDocs Material → Zensical.

## Suggested opening prompt for the next session

> Continue LedgerLens: start P1 per HANDOFF.md.
