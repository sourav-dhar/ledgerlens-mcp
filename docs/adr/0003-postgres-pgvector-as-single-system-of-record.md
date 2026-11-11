# PostgreSQL with pgvector is the single system of record

Banking data, the double-entry ledger, idempotency records, the outbox, the audit log and document embeddings all live in one RDS PostgreSQL instance. A ledger needs ACID transactions, joins and aggregates; pgvector puts retrieval in the same database, so hybrid search, row-level security on document classification and transactional writes share one engine.

## Considered Options

- **DynamoDB single-table + DuckDB over Parquet**: near-zero idle cost, but ad-hoc filtering and aggregation fight the access-pattern model.
- **S3 Vectors**: not available on this AWS plan.
- **OpenSearch Serverless**: about $170/month minimum.
- **LanceDB on S3**: cheap, but a second datastore with no transactional link to the domain.

DynamoDB is kept only for hot control state: per-client rate limits and circuit-breaker overrides.
