# Domain events leave through a transactional outbox onto SQS; no Kafka

Writes insert an event row into `ops.outbox` inside the business transaction; a relay publishes unpublished rows to SQS, and consumers are idempotent. This removes the dual-write problem (commit succeeds, publish fails) without distributed transactions. SQS with dead-letter queues also carries document ingestion, giving backpressure against embedding-provider rate limits.

## Considered Options

- **Amazon MSK (Kafka)**: requires the paid plan, costs hundreds per month, and nothing here needs ordered high-throughput streams or replay.
- **Publish directly after commit**: simpler, but loses events whenever the process dies between the two steps.
