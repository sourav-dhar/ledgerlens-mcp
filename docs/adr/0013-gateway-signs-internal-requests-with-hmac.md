# The gateway signs its requests to `core-api` with an HMAC over the request and the principal

`core-api` trusts the principal the gateway authenticated (its `sub` and knowledge-base ceiling), so it needs proof that a request came from the gateway and was not altered. The gateway sends the principal in `X-Kosha-Actor` and `X-Kosha-Kb-Ceiling`, with `X-Kosha-Timestamp` and `X-Kosha-Signature: v1=<hex>`. The signature is an HMAC-SHA256, keyed by a secret both services read from Secrets Manager, over the timestamp, method, target (path and query as sent), both principal headers and the SHA-256 of the body. `core-api` accepts a timestamp within 60 seconds of its clock, tries every configured key (current first, then the previous one during a rotation), and fails closed with `401` when no key is configured. The scheme lives in `kosha_domain.signing`, so both services share one implementation.

## Considered Options

- **A shared bearer token**: simplest, but the secret crosses the wire on every call and lands wherever headers are logged. It also proves only "someone with the token", so a captured request could be edited to act for a different principal or a higher ceiling.
- **Mutual TLS**: strong, but Lambda Function URLs and the Lambda Web Adapter do not terminate client certificates, so it would need a load balancer in front of `core-api` and a private CA to run.
- **IAM SigV4 through a private API Gateway**: no shared secret to rotate, at the cost of an extra hop, API Gateway pricing and a SigV4-signing client in the gateway. It remains the candidate for P6 (LLD security §3); the principal headers would then still need their own integrity, which this scheme already gives.

## Consequences

- There is no nonce store: a captured request can be replayed within the 60-second window. Reads are harmless to replay, and every write already carries an idempotency key (ADR 0007), so a replayed write returns the first response.
- Rotation is add-then-remove: deploy `core-api` with `new,old`, switch the gateway to `new`, then drop `old`.
- Anything between the services that rewrites the path, the query or the body breaks the signature. The target is signed exactly as sent, so the gateway must sign the final encoded URL (an httpx auth flow does this).
- Health probes and the OpenAPI document stay unauthenticated; every `/v1` route requires a valid signature.
