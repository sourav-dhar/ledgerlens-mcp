# LedgerLens MCP

**A production-grade [Model Context Protocol](https://modelcontextprotocol.io) server for Kosha Financial**, a fictional Indian neobank. AI agents use it to investigate customers, payments, KYC and AML alerts, take audited write actions, and search 85 internal policies and SOPs.

!!! note "Everything here is synthetic"
    Kosha Financial, its staff and its customers are fictional. Real Indian regulations (RBI KYC Master Direction, PMLA, DPDP Act) are cited for realism; nothing is legal or compliance advice.

## What it demonstrates

<div class="grid cards" markdown>

-   :material-shield-lock-outline: **OAuth 2.1, done to spec**

    MCP Authorization with RFC 9728 discovery, Cognito, per-tool scopes, role-based PII masking and an append-only audit log.

-   :material-electric-switch: **Resilience you can watch**

    Deadlines, retries with jitter and budgets, circuit breakers, bulkheads, rate limits, idempotency and chaos injection.

-   :material-database-search-outline: **Hybrid RAG with citations**

    pgvector + Postgres full-text fused by RRF, row-level security on document classification, graceful fallback.

-   :material-aws: **Serverless on AWS**

    Lambda container images, CDK, OIDC deploys and CodeDeploy canaries with automatic rollback.

</div>

## Where to start

| If you want to… | Read |
|---|---|
| See the whole system on one page | [High-level design](architecture/hld.md) |
| Understand a design choice | [Architecture decisions](adr/index.md) |
| Learn the domain language | [Glossary](glossary.md) |
| Follow how the design evolved | [Plans](plans/CHANGELOG.md) |
