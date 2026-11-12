# Architecture

Design documentation for **LedgerLens MCP**, the Model Context Protocol server for Kosha Financial (a fictional Indian neobank).
Decisions trace back to [plan v1.0](../plans/v1.0-architecture.md) and [data model v0.2](../plans/v0.2-data-model-and-corpus.md); lasting trade-offs live in [ADRs](../adr/index.md).

## High-level design

| Document | Covers |
|---|---|
| [HLD](hld.md) | System context, containers, AWS deployment, request & auth flows, SLOs, cost, trade-offs |

## Low-level design

| Document | Covers |
|---|---|
| [MCP gateway](lld/mcp-gateway.md) | Middleware pipeline, tool contracts, error taxonomy, cursor signing, scopes |
| [Core API](lld/core-api.md) | Routers, repositories, transaction boundaries, outbox, idempotency, ledger posting |
| [Data model](lld/data-model.md) | ER diagrams, status lifecycles, indexes, partitioning, RLS, PII handling |
| [Resilience](lld/resilience.md) | Deadlines, retry, circuit breaker, bulkhead, rate limiting, load shedding, chaos |
| [RAG pipeline](lld/rag-pipeline.md) | Ingestion, chunking, embeddings, hybrid retrieval SQL, evals, injection defences |
| [Async messaging](lld/async-messaging.md) | Transactional outbox, relay, idempotent consumers, DLQ handling |
| [Security](lld/security.md) | STRIDE threat model, secrets, KMS envelope encryption, audit, OWASP LLM Top 10 |
| [Deployment & CI/CD](lld/deployment-cicd.md) | GitHub Actions, OIDC, image strategy, CodeDeploy canary, rollback |
| [Observability](lld/observability.md) | OpenTelemetry signal flow, RED metrics, log schema, dashboards, alarms |

## Reading order

1. HLD for the shape of the system.
2. MCP gateway and Core API for the request path.
3. Data model for what is stored and why.
4. Resilience, async messaging and RAG for behaviour under load and failure.
5. Security, deployment and observability for running it in production.
