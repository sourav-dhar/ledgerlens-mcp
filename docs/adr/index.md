# Architecture decisions

Each record captures a decision that is hard to reverse, would surprise a newcomer, and came out of a real trade-off. Easily reversible or obvious choices are deliberately not recorded.

| # | Decision |
|---|---|
| [0001](0001-mcp-gateway-calls-core-api-over-http.md) | The MCP gateway calls the Core Banking API over HTTP |
| [0002](0002-lambda-container-images-over-fargate.md) | Lambda container images, not ECS Fargate |
| [0003](0003-postgres-pgvector-as-single-system-of-record.md) | PostgreSQL with pgvector is the single system of record |
| [0004](0004-jwt-validated-in-app-not-api-gateway.md) | Access tokens are validated in the application, not by API Gateway |
| [0005](0005-nat-instance-not-nat-gateway.md) | A NAT instance, not a NAT Gateway, provides egress |
| [0006](0006-per-instance-breakers-with-shared-override.md) | Circuit breakers are per instance, with a shared force-open override |
| [0007](0007-idempotency-in-the-write-transaction.md) | Idempotency records are written in the same transaction as the business change |
| [0008](0008-transactional-outbox-and-sqs-no-kafka.md) | Domain events leave through a transactional outbox onto SQS; no Kafka |
| [0009](0009-openai-embeddings-with-fts-degradation.md) | OpenAI embeddings, with full-text search as the degraded mode |
| [0010](0010-codedeploy-canary-from-github-actions.md) | Deploy with GitHub Actions and CodeDeploy canaries, not CodePipeline |
| [0011](0011-composite-foreign-keys-to-partitioned-transactions.md) | Rows that reference a Transaction carry its `initiated_at` in a composite foreign key |
| [0012](0012-opening-balances-gl-for-balances-brought-forward.md) | Balances older than the ledger are brought forward against an `opening_balances` GL account |
