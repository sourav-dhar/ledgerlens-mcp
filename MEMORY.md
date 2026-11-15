# Project memory

> Durable lessons that are not yet a rule ([CLAUDE.md](CLAUDE.md)) or a decision ([docs/adr](docs/adr/index.md)). Newest first within each section. Promote an entry to CLAUDE.md or an ADR once it governs future work, then delete it here.

## Lessons learned

- **2026-11-14 — A dependency that raises pre-empts FastAPI validation.** FastAPI resolves dependencies before it reports invalid query parameters, so a "database configured?" dependency answered `503` to malformed input. Inject `Database | None` and check it inside the handler (`deps.require`).
- **2026-11-14 — The Lambda Web Adapter's readiness check gates every cold start.** Pointing it at a readiness probe that checks the database would stop new instances starting during a database outage. The adapter waits on `/healthz`; `/readyz` is for orchestrators and humans.
- **2026-11-14 — Async psycopg cannot run on the Windows Proactor loop.** The root `anyio_backend` fixture uses `asyncio.SelectorEventLoop` on `win32`; CI on Linux is unaffected.
- **2026-11-14 — One `set_config` round trip sets a whole transaction context.** `role`, `transaction_read_only`, `statement_timeout` and custom `kosha.*` settings can all be set with `set_config(name, value, true)` in a single `SELECT`, after `BEGIN`; all of them end with the transaction.
- **2026-11-14 — syrupy writes snapshots with CRLF on Windows.** The `mixed-line-ending` hook then rewrites them and fails the commit. Convert a regenerated snapshot to LF before staging it.
- **2026-11-14 — Splitting a commit trips the whole-tree pyright hook.** pre-commit stashes unstaged changes to tracked files but leaves untracked files in place, so an untracked test that depends on an unstaged edit fails type-checking. Move such files aside for the first commit, or stage the helper they need.
- **2026-11-14 — Scripted edits wrote CRLF again.** The `write_text` lesson below still applies to ad-hoc `python3 -` edits: use `read_bytes`/`write_bytes`.
- **2026-11-12 — Per-row triggers dominated the bulk load.** Foreign-key checks into the partitioned `core.transactions` and the deferred balance triggers made `COPY` 11× slower (145 s against 13 s per 200 Customers) and the full seed about an hour. Benchmark with `session_replication_role = replica` before optimising anything else; if triggers are the cost, load without them and prove the same guarantees set-based afterwards (`kosha_datagen.reconcile`).
- **2026-11-12 — Rupees leak into paise inside arithmetic, not at boundaries.** The generator computed take-home pay in rupees and passed it as paise, so salaries arrived as ₹307. Types cannot catch it (both are `int`); a distribution test (transactions per Customer by persona) did. Suffix intermediate variables with their unit too, and keep a volume test per persona.
- **2026-11-12 — A dict keyed by status loses revisited statuses.** A held-then-cleared Transaction passes `processing` twice; keying timestamps by status silently dropped the first visit and broke history order. Status histories are ordered lists of `(status, at)`.
- **2026-11-12 — psycopg `COPY` adapts a `StrEnum` as its value** (`str` precedes `Enum` in the MRO), but a `dict` needs an explicit `Jsonb` wrapper.
- **2026-11-12 — The pre-commit pyright hook checks untracked files too.** It runs over the whole tree, so writing a half-finished module while a background commit runs can fail that commit. Wait for the commit before creating files.
- **2026-11-12 — Make planted test conditions deterministic.** Bad actors drawn by a 2% coin flip made "every typology fires" depend on luck at test scale; choosing them by index (`i % 50 == 16`, typologies in rotation) guarantees coverage at 350 Customers without exposing anything in the data.
- **2026-11-12 — Partitioned tables cannot promise uniqueness on other columns.** Every unique index must include the partition key, so `UNIQUE (utr, initiated_at)` only forbids duplicates at the same instant. Prefer a plain index and say so, over a constraint that looks stronger than it is.
- **2026-11-12 — A table with pending deferred-trigger events cannot be truncated.** Postgres raises `ObjectInUse` before any `BEFORE TRUNCATE` trigger runs, so a test of a truncate guard must run before inserting rows in that transaction.
- **2026-11-12 — `importlib` import mode cannot import sibling test modules.** Shared test helpers live in `tests/support/` (fixtures load as a plugin from the root `conftest.py`), added to pytest's `pythonpath` and pyright's `extraPaths`, with a distinctive module name (`db_rows`).
- **2026-11-12 — testcontainers moved its Postgres module.** `testcontainers.postgres` emits a `DeprecationWarning` (an error here); import from `testcontainers.community.postgres`.
- **2026-11-12 — psycopg wants `LiteralString` queries.** Parametrised SQL in tests is annotated `LiteralString`; dynamic identifiers go through `psycopg.sql.Identifier`, never f-strings.
- **2026-11-12 — gitleaks flags synthetic tokens.** A random-looking value under a key like `token_ref` trips `generic-api-key`; use plainly fake values (`card-token-for-tests`) rather than allow-listing.
- **2026-11-12 — Generate frozen literals, then guard them.** Enum labels and the 127 lifecycle edges were generated once from `kosha-domain` and pasted into the revision; parity tests keep them honest. Hand-typing them invites typos no reviewer will catch.
- **2026-11-12 — Test the code against the design doc.** Parsing the LLD's Mermaid state diagrams in a test and requiring an exact edge match turns the diagram into an executable spec; doc and code can no longer drift silently. Reuse the pattern wherever a diagram encodes rules.
- **2026-11-12 — Commit chains outlast the tool timeout.** The pre-commit hook runs strict pyright per commit, so three or more commits in one call exceed two minutes. Run commit chains in the background, and do not edit tracked files meanwhile: pre-commit stashes unstaged changes while its hooks run.
- **2026-11-12 — `Path.write_text` writes CRLF on Windows.** Scripted edits to tracked files must use `write_bytes` (or `newline="\n"`), or the diff shows every line changed.
- **2026-11-12 — ruff ERA001 reads parentheses as code.** A divider comment such as `# --- RRN (UPI, IMPS, card)` is flagged as commented-out code; write dividers without parenthesised lists.
- **2026-11-12 — Rate limit after authentication.** Keying a pre-auth limit on an unverified `client_id` claim lets a forged token exhaust a victim's bucket. Authenticate, then rate-limit on the verified identity; edge throttling absorbs anonymous floods.
- **2026-11-12 — Review rendered diagrams, not their source.** Generated Excalidraw JSON looked fine but rendered with overlapping labels and two factual errors ("signed" images, "bandit"). Render via Kroki, screenshot with headless Edge, read the PNG.
- **2026-11-12 — Validate Mermaid with Mermaid.** `mkdocs build --strict` does not parse diagrams. Parsing every block with `mermaid.parse` in headless Edge catches syntax errors before readers do.
- **2026-11-12 — release-please does not touch uv.lock.** Version bumps in `pyproject.toml` left the lockfile stale and `uv sync --locked` failed on the release PR. A release-workflow job re-locks the release branch.
- **2026-11-12 — Release PRs need a PAT.** PRs opened with `GITHUB_TOKEN` do not trigger CI. A fine-grained PAT (`RELEASE_PLEASE_TOKEN`: Contents + Pull requests read/write, this repo only) does; it expires 2027-02-10.
- **2026-11-12 — Official Python images lag Debian security fixes.** Trivy failed all images on fixable perl/openssl/sqlite CVEs; the runtime stage now applies Debian security updates.
- **2026-11-12 — Reproducible venv layer.** uv's `uv_cache.json` (source timestamps) made the venv layer change on every code edit; stripping it took code-only rebuilds from 155 s to 7 s.
- **2026-11-12 — Coverage must measure by package.** `source = ["services"]` silently skipped never-imported modules; `source_pkgs` reports every file.
- **2026-11-12 — MCP SDK v2 is snake_case.** `read_only_hint`, `server_info`, `output_schema`; camelCase access warns, and warnings are errors here.
- **2026-11-12 — pytest-asyncio breaks FastMCP lifespans.** Fixture setup and teardown run in different tasks; AnyIO's plugin keeps them in one.

## Incidents

- **2026-11-14 — Full seed stopped at about 600 Customers.** Docker's memory was needed for other work, and C: fell from 22 GB to 7 GB free in ten minutes while Postgres held 1.4 GB, so something outside this repo was writing to the drive. Remedy: check free space and other heavy jobs before a long run, and keep the seed for a time when the machine is otherwise idle.
- **2026-11-12 — Workstation ran out of memory.** Three Docker jobs in parallel (Kroki, Mermaid CLI with Chromium, image previews) exhausted the commit limit and required a reboot. Remedy: WSL capped at 3 GB; heavy containers run sequentially and are stopped after use; browser-based checks use the installed Edge instead of containerised Chromium.

## Deferred

- **Find a Transaction by ID without probing every partition.** `GET /v1/transactions/{id}` checks each monthly partition's primary-key index. If the generator and the write path guarantee that a `txn_` ULID's timestamp equals `initiated_at`, the month can be derived from the ID and the lookup pruned to one partition.
- **Commit a Mermaid validation script.** Done ad hoc twice now (headless Edge + `mermaid.parse`); a `poe docs-check` task would make it repeatable and catch escaping slips in the throwaway page.
- **Distroless runtime image** — removes apt/perl/shell CVE classes and shrinks the image; costs a rework of how the venv is copied and shell-less debugging. Candidate ADR.
- **Image signing and SBOM attestation** (cosign / GitHub attestations) once images are pushed to ECR in P6.
- **MkDocs Material reaches end of life on 2027-05-05**; its successor Zensical reads `mkdocs.yml`. Revisit in P8.
- **Breaker and RRF parameters** in the diagrams (≥ 50% of 20 calls, 30 s cool-down, 3 trial calls, k = 60) are placeholders to confirm in P4/P5.
