# syntax=docker/dockerfile:1
#
# One image recipe for every service in the uv workspace.
#
#   docker build -f docker/Dockerfile --build-arg SERVICE=mcp-gateway -t ledgerlens/mcp-gateway .
#
# The same image runs under docker compose and on AWS Lambda: the Lambda Web Adapter
# extension (inert outside Lambda) translates Lambda invocations into HTTP on $PORT.
#
# Layering, from least to most frequently changed:
#   1. base images pinned by digest (Dependabot bumps them)
#   2. third-party dependencies, keyed only on pyproject.toml + uv.lock
#   3. the service's own source code

ARG PYTHON_IMAGE=python:3.13.13-slim-trixie@sha256:aa938a849bcb82dce8f49480f056ab82bf5c1c3ebc294f0430f37b6820e7f286
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490
ARG LWA_IMAGE=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1

FROM ${UV_IMAGE} AS uv
FROM ${LWA_IMAGE} AS lambda-adapter

# ---------------------------------------------------------------------------
# manifests: the workspace reduced to pyproject.toml files and the lockfile,
# so source edits never invalidate the dependency layer below.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS manifests
WORKDIR /src
COPY . .
RUN find . -type f ! -name pyproject.toml ! -name uv.lock -delete \
 && find . -type d -empty -delete

# ---------------------------------------------------------------------------
# builder: resolve and install into /app/.venv with uv
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

ARG SERVICE
RUN test -n "${SERVICE}" || (echo "build-arg SERVICE is required" >&2 && exit 1)

WORKDIR /src

# Layer 2: third-party dependencies only.
COPY --from=manifests /src/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package "kosha-${SERVICE}"

# Layer 3: register the service and the shared packages it depends on. Editable installs
# write only a .pth file and metadata pointing at /src/{services,packages}/<name>/src, so the
# venv is byte-identical across code changes and the runtime stage's venv layer stays cached.
# Source is copied separately.
COPY packages/ packages/
COPY services/${SERVICE}/ services/${SERVICE}/
# uv_cache.json records source timestamps for uv's own cache invalidation and is unused at
# runtime; dropping it (and its RECORD line) from every workspace member's metadata makes
# this layer reproducible bit for bit.
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_COMPILE_BYTECODE=0 uv sync --frozen --no-dev --package "kosha-${SERVICE}" \
 && for dist_info in /app/.venv/lib/python3.13/site-packages/kosha_*.dist-info; do \
      rm -f "${dist_info}/uv_cache.json" \
      && sed -i '/uv_cache\.json/d' "${dist_info}/RECORD" || exit 1; \
    done

# ---------------------------------------------------------------------------
# runtime: no uv, no compilers, no source tree, no root.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ARG SERVICE
LABEL org.opencontainers.image.title="ledgerlens-${SERVICE}" \
      org.opencontainers.image.description="LedgerLens MCP: ${SERVICE}" \
      org.opencontainers.image.source="https://github.com/sourav-dhar/ledgerlens-mcp" \
      org.opencontainers.image.licenses="MIT"

# Debian publishes security fixes before the official Python image is rebuilt; apply them so
# the image ships with no fixable HIGH/CRITICAL CVEs (Trivy gates this in CI). The base digest
# stays pinned; only security patches float, and Dependabot moves the base forward weekly.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* /var/log/apt/* /var/log/dpkg.log \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=lambda-adapter /lambda-adapter /opt/extensions/lambda-adapter

# Owned by root and only readable by the app user: the running process cannot modify its own code.
# Large, rarely changing layer: third-party packages (already compiled to bytecode).
COPY --from=builder /app/.venv /app/.venv
# Small, frequently changing layers: shared packages and the service source, precompiled
# because Lambda's filesystem is read-only and Python could otherwise not cache bytecode.
COPY packages/ /src/packages/
COPY services/${SERVICE}/src/ /src/services/${SERVICE}/src/
RUN python -m compileall -q /src

# The adapter's readiness check gates every cold start, so it probes liveness: a check on
# /readyz would hold every new instance hostage to the database.
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/healthz \
    AWS_LWA_READINESS_CHECK_HEALTHY_STATUS=200 \
    AWS_LWA_READINESS_CHECK_TIMEOUT_SECONDS=9

USER 10001:10001
WORKDIR /app
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ['PORT']}/healthz\", timeout=2)"]

ENTRYPOINT ["kosha-serve"]
