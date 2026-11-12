# High-Level Design

> Source of truth: [plan v1.0](../plans/v1.0-architecture.md). This document explains the shape; the plan records the decisions.

## 1. Purpose and scope

LedgerLens MCP lets AI agents work with Kosha Financial's operational data and internal knowledge through the Model Context Protocol:

| Capability | Tools |
|---|---|
| Customer & KYC lookup | `search_customers`, `get_customer_profile`, `get_kyc_status`, `list_kyc_documents` |
| Accounts & payments | `get_account_summary`, `search_transactions`, `get_transaction`, `get_spending_insights` |
| Risk & compliance | `list_aml_alerts`, `get_aml_alert`, `screen_entity` |
| Audited writes | `raise_dispute`, `flag_transaction_for_review` |
| Knowledge | `search_knowledge_base`, `get_document` |
| Operations | `get_service_health` |

Out of scope: moving real money, real customer data, multi-Region operation (not available to the project).

## 2. System context (C4 level 1)

```mermaid
flowchart LR
    analyst["Ops / compliance staff<br/>(human)"]
    agent["AI agent<br/>LangGraph copilot, Google ADK,<br/>Claude Desktop"]
    lm["LedgerLens MCP<br/>(this system)"]
    cognito["Amazon Cognito<br/>(authorization server)"]
    openai["OpenAI API<br/>(embeddings)"]
    vendor["Sanctions / PEP vendor<br/>(simulated: screening-sim)"]

    analyst -->|"asks questions"| agent
    agent -->|"MCP over Streamable HTTP + OAuth 2.1 bearer"| lm
    agent -->|"OAuth 2.1 + PKCE / client credentials"| cognito
    lm -->|"validates JWT via JWKS"| cognito
    lm -->|"embed queries and chunks"| openai
    lm -->|"screen names"| vendor
```

*Notice: the agent never talks to data stores directly; every capability is mediated by one OAuth-protected MCP endpoint.*

## 3. Containers (C4 level 2)

```mermaid
flowchart TB
    subgraph clients["Clients"]
        copilot["LangGraph copilot + Streamlit console"]
        adk["Google ADK agent"]
        desktop["Claude Desktop"]
    end

    openai["OpenAI API"]

    subgraph ledgerlens["LedgerLens MCP"]
        gw["mcp-gateway<br/>FastMCP, Streamable HTTP<br/>authn, scopes, masking, audit, rate limit"]
        api["core-api<br/>FastAPI<br/>domain logic, persistence, retrieval"]
        sim["screening-sim<br/>FastAPI vendor simulator"]
        ingest["ingest-worker<br/>parse, chunk, embed"]
        relay["outbox-relay<br/>publishes ops.outbox"]
        events["events-worker<br/>dispute SLA, review fan-out"]
        pg[("PostgreSQL 16 + pgvector<br/>core, ledger, kyc, risk, ops, kb")]
        ddb[("DynamoDB<br/>rate-limit buckets, breaker overrides")]
        q1[["SQS ingest-queue + DLQ"]]
        q2[["SQS domain-events + DLQ"]]
        s3[("S3<br/>corpus source documents")]
    end

    copilot & adk & desktop -->|"MCP"| gw
    gw -->|"HTTP, deadline header"| api
    gw -->|"HTTP via breaker"| sim
    gw -->|"token bucket, overrides"| ddb
    api --> pg
    api -->|"embeddings"| openai
    s3 -->|"object created"| q1 --> ingest --> pg
    ingest --> openai
    relay -->|"poll unpublished"| pg
    relay --> q2 --> events --> pg
```

*Notice: the gateway owns cross-cutting concerns (auth, masking, audit, rate limits); `core-api` owns all domain state; asynchronous work never blocks a tool call.*

| Container | Runtime | Owns |
|---|---|---|
| `mcp-gateway` | FastMCP on Lambda (Web Adapter) | Protocol, auth, authorization, masking, audit, rate limiting, resilience toward downstreams |
| `core-api` | FastAPI on Lambda (Web Adapter) | Domain rules, Postgres schemas, ledger, outbox, idempotency, hybrid retrieval |
| `screening-sim` | FastAPI on Lambda | Simulated external dependency with tunable latency and failure |
| `ingest-worker` | Lambda, SQS trigger | Document parsing, chunking, embedding, upsert |
| `outbox-relay` | Lambda, scheduled | Exactly-once-effect publication of domain events |
| `events-worker` | Lambda, SQS trigger | Dispute TAT timers, review queue fan-out |

## 4. Deployment view (AWS, `eu-north-1`)

```mermaid
flowchart TB
    user["MCP client"] --> cf["CloudFront<br/>(global)"]

    subgraph region["eu-north-1"]
        apigw["API Gateway HTTP API"]
        simfn["Lambda: screening-sim"]

        subgraph vpc["VPC"]
            subgraph priv["Private subnets"]
                gwfn["Lambda: mcp-gateway<br/>alias live"]
                apifn["Lambda: core-api<br/>alias live"]
                ingestfn["Lambda: ingest-worker"]
                relayfn["Lambda: outbox-relay"]
                eventsfn["Lambda: events-worker"]
                rds[("RDS PostgreSQL 16<br/>db.t4g.micro, single-AZ")]
            end
            subgraph pub["Public subnet"]
                nat["NAT instance<br/>t4g.nano"]
            end
            gwep["Gateway endpoints<br/>S3, DynamoDB"]
        end

        apigw --> gwfn
        apigw --> simfn
        gwfn --> apifn
        apifn --> rds
        ingestfn --> rds
        relayfn --> rds
        eventsfn --> rds
        gwfn --> gwep
        ingestfn --> gwep
        priv -->|"OpenAI, Cognito JWKS,<br/>Secrets Manager"| nat
        nat --> igw["Internet gateway"]

        ddb[("DynamoDB")]
        sqs[["SQS + DLQs"]]
        s3[("S3 corpus bucket")]
        sm["Secrets Manager<br/>OpenAI key, DB credentials,<br/>chaos HMAC key"]
        cognito["Cognito user pool"]
        cw["CloudWatch + X-Ray"]
        cd["CodeDeploy<br/>canary 10% / 5 min"]
        ecr["ECR (arm64 images)"]
    end

    cf --> apigw
    gwep --> ddb
    gwep --> s3
    s3 --> sqs
    cd -.->|"shifts alias traffic"| gwfn
    cd -.-> apifn
    cw -.->|"alarm triggers rollback"| cd
```

*Notice: everything Regional is in `eu-north-1`; only CloudFront is global. S3 and DynamoDB traffic stays on free gateway endpoints; only internet-bound calls pay for the NAT instance.*

Network rules:

| From | To | Path |
|---|---|---|
| Lambdas in VPC | RDS | Security group to security group, port 5432 |
| Lambdas in VPC | S3, DynamoDB | Gateway VPC endpoints (no NAT cost) |
| Lambdas in VPC | OpenAI, Cognito JWKS, Secrets Manager, SQS | NAT instance |
| `screening-sim` | none | Runs outside the VPC; it has no private dependencies |

## 5. Request lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant A as Agent (MCP client)
    participant G as mcp-gateway
    participant D as DynamoDB
    participant C as core-api
    participant P as PostgreSQL
    participant O as OpenAI

    A->>G: tools/call search_knowledge_base (Bearer JWT)
    G->>D: Token bucket: conditional decrement for client_id
    D-->>G: Allowed (tokens remaining)
    G->>G: Validate JWT (cached JWKS), check scope kb:read
    G->>G: Start deadline budget (e.g. 8 s), open trace span
    G->>C: POST /v1/kb/search (X-Request-Deadline, traceparent)
    C->>O: Embed query (timeout = min(remaining - margin, 2 s))
    O-->>C: 1024-dim vector
    C->>P: set kb_ceiling = confidential, then hybrid RRF query
    P-->>C: Top-k chunks (RLS-filtered)
    C-->>G: Chunks with citations, degraded=false
    G->>G: Mask fields per role, cap payload size
    G->>C: POST /v1/audit (actor, tool, args_hash, outcome, latency)
    C->>P: INSERT ops.audit_log
    G-->>A: Tool result (structured content + text)
```

*Notice: every hop receives the remaining deadline, so a slow embedding call cannot push the overall request past its budget.*

If OpenAI fails or the deadline is too short for embedding, `core-api` runs the full-text half of the query only and returns `degraded: true`.

## 6. Authorization discovery

```mermaid
sequenceDiagram
    autonumber
    participant A as MCP client
    participant G as mcp-gateway (resource server)
    participant X as FastMCP OAuth proxy
    participant K as Cognito

    A->>G: POST /mcp (no token)
    G-->>A: 401 + WWW-Authenticate: Bearer resource_metadata=".../.well-known/oauth-protected-resource"
    A->>G: GET /.well-known/oauth-protected-resource
    G-->>A: RFC 9728 metadata (authorization_servers, scopes_supported)
    A->>X: GET /.well-known/oauth-authorization-server
    X-->>A: Endpoints (authorize, token, register)
    A->>X: POST /register (dynamic client registration)
    X-->>A: client_id (proxied to a pre-registered Cognito app client)
    A->>X: /authorize with PKCE (code_challenge, scopes)
    X->>K: Redirect to Cognito managed login
    K-->>X: Authorization code
    X-->>A: Code (bound to the client's PKCE challenge)
    A->>X: /token (code_verifier)
    X->>K: Exchange code
    K-->>X: Access token (JWT, aud = gateway, scope, cognito:groups)
    X-->>A: Access token
    A->>G: POST /mcp (Bearer JWT)
    G-->>A: 200 tool result
```

*Notice: Cognito does not support dynamic client registration, so FastMCP's OAuth proxy supplies it while Cognito stays the real identity provider. Service-to-service callers skip the browser flow and use client credentials.*

## 7. Quality attributes

| Attribute | Target | Mechanism | Verified by |
|---|---|---|---|
| Latency, simple reads | p95 < 300 ms warm | Indexed queries, connection reuse per instance, payload caps | Locust in CI against deployed stack |
| Latency, KB search | p95 < 900 ms | HNSW index, single SQL round trip, 1024-dim embeddings | Locust, RAG eval suite |
| Cold start | < 2.5 s | Slim arm64 images, lazy imports, no work at import time | Synthetic probe after deploy |
| Availability | 99.5% | Canary + rollback, breakers, degradation, retries with budget | CloudWatch SLO alarms |
| Fairness | 60 req/min/client, burst 20 | DynamoDB token bucket | Integration tests, Locust |
| Correctness of money | Ledger reconciles to the paisa | Double-entry postings, `BIGINT` paise, nightly reconciliation test | Property tests, reconciliation job |
| Confidentiality | No PII beyond scope | Scope checks, masking, RLS on KB classification | Per-tool failure matrix |

## 8. Cost (approximate, monthly, while running)

| Item | Cost |
|---|---|
| RDS PostgreSQL `db.t4g.micro` + 20 GB gp3 | ~$15 |
| NAT instance `t4g.nano` + public IPv4 | ~$7 |
| Lambda, API Gateway, CloudFront, SQS, DynamoDB at demo volume | ~$1 |
| Secrets Manager (3 secrets) | ~$1.20 |
| CloudWatch logs, metrics, X-Ray | ~$1 |
| **Total** | **≈ $25** |

`poe pause` stops RDS and the NAT instance between demos; `poe resume` starts them again.

## 9. Key trade-offs

| Decision | Alternative rejected | Why | ADR topic |
|---|---|---|---|
| Lambda container images | ECS Fargate | ~2.5x cheaper idle; same image runs anywhere | Compute platform |
| Separate gateway and core API | Single FastMCP process | Real network seam makes resilience patterns meaningful and keeps protocol concerns out of the domain | Service split |
| PostgreSQL as system of record | DynamoDB single-table | Ledger needs ACID, joins, aggregates; pgvector needs Postgres anyway | Datastore |
| pgvector + FTS hybrid in one query | OpenSearch Serverless, S3 Vectors | OpenSearch ~$170/month minimum; S3 Vectors unavailable on the plan | Vector store |
| NAT instance | NAT Gateway | ~$7 vs ~$33/month; single point of failure accepted for a demo | Egress |
| In-memory breakers + DynamoDB override | Fully shared breaker state | Avoids a network call per request; override covers fleet-wide incidents | Breaker state |
| In-app JWT validation | API Gateway JWT authorizer | Spec requires `WWW-Authenticate` with resource metadata on 401 | Auth placement |
| SQS + transactional outbox | Kafka / MSK | No streaming workload; MSK not on the plan | Messaging |
| CodeDeploy canary | All-at-once deploy | Alarm-driven automatic rollback | Deployment safety |
