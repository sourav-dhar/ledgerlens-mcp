# Rate limits are layered, weighted by tool cost, keyed on the verified principal, and fail soft

A single per-client bucket of 60 requests a minute (plan v1.0 §5) treats a cheap profile lookup like a paid embedding call or a write, lets one agent fleet sharing an OAuth client starve every user behind it, does nothing about anonymous floods, and disappears entirely when DynamoDB is unavailable (it failed open). Rate limiting is therefore layered (resilience LLD §6). API Gateway throttling, and optionally a WAF rate-based rule, absorb floods before any code runs. After the JWT is validated, the gateway charges each call to two token buckets in DynamoDB, one per principal `(client_id, sub)` and one per client, taking 1, 2, 3 or 5 tokens according to the tool's cost. Outbound quotas protect OpenAI and the screening vendor by degrading, not queueing. Lambda reserved concurrency and SQS maximum concurrency cap what can reach the database. When DynamoDB is unavailable, each instance falls back to an in-memory bucket with the same parameters.

## Considered Options

- **One bucket per client (v1.0)**: simplest, but blind to cost and identity, and unlimited during a DynamoDB outage.
- **Fail closed when DynamoDB is down**: strictly fair, but it turns an outage of a supporting service into an outage of every tool.
- **Fail open (v1.0)**: available, but unbounded exactly when the system is already degraded.
- **Limit before authentication on the token's claims**: cheaper, but an attacker presenting someone else's unverified `client_id` could drain their bucket (MEMORY.md, 2026-11-12). Anonymous excess is the edge layers' job instead.
- **API Gateway usage plans and API keys**: only on REST APIs, not the HTTP API in front of the gateway, and keyed on API keys rather than OAuth identities.
- **A sliding-window log in Redis**: exact, but ElastiCache costs more than the whole stack and adds a dependency to keep healthy.

## Consequences

- During a DynamoDB outage the effective limit is the per-instance limit times the number of warm instances, at most 20 (reserved concurrency): bounded, metered and alarmed, where v1.0 was unlimited.
- Each tool call costs two conditional DynamoDB writes, issued in parallel over the gateway endpoint (single-digit milliseconds).
- A rejected call is an HTTP `429` before MCP dispatch, with `Retry-After` and the IETF `RateLimit-Policy` / `RateLimit` fields, so well-behaved agents can pace themselves without trial and error.
- The WAF layer costs a few dollars a month and may not be on the account's plan; the design does not depend on it, because API Gateway throttling is the required flood guard.
