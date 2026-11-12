# Contributing

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
uv sync --all-packages                      # Python 3.13 + every workspace package
uv run pre-commit install --install-hooks   # format, lint, type-check, secret scan, commit-message check
uv run poe up                               # local stack: gateway :8700, core API :8701, screening :8702
```

`uv run poe --help` lists every task. `uv run poe check` runs what CI runs on each push.

## Workflow

1. Read the relevant design doc in [`docs/architecture/`](docs/architecture/index.md) and the [glossary](GLOSSARY.md).
2. Write a failing test first, make it pass, then refactor.
3. Keep the gates green: `ruff`, `pyright --strict` at zero errors, `pytest` (warnings are errors), coverage ≥ 90%.
4. Commit with [Conventional Commits](https://www.conventionalcommits.org): `type(scope): summary`, where scope is a service (`mcp-gateway`, `core-api`, …) or an area (`docker`, `ci`, `adr`, `plans`). Explain *why* in the body.
5. Record hard-to-reverse decisions as an ADR in [`docs/adr/`](docs/adr/index.md).

## Pull requests

CI must pass: lint and types, tests with coverage, dependency audit, secret scan, arm64 image build with smoke test and Trivy scan, and a strict docs build.
