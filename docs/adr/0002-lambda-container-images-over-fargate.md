# Lambda container images, not ECS Fargate

Every service ships as one arm64 container image run on AWS Lambda through the Lambda Web Adapter, so FastAPI and FastMCP run unmodified and the same image runs in `docker compose`. Lambda scales to zero (about $25/month total versus about $65 on Fargate with a load balancer), which decides it for a demo that is idle most of the time.

## Consequences

- MCP uses stateless Streamable HTTP with JSON responses; no long-lived SSE streams.
- Circuit-breaker state is per execution environment (see ADR-0006).
- Postgres connections are bounded with small per-instance pools and reserved concurrency instead of RDS Proxy.
- Moving to Fargate later is an infrastructure change only: the image already serves HTTP on `$PORT`.
