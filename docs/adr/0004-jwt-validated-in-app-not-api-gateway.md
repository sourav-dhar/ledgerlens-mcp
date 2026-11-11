# Access tokens are validated in the application, not by API Gateway

The MCP Authorization spec requires a `401` with a `WWW-Authenticate` header pointing at the RFC 9728 Protected Resource Metadata so clients can discover the authorization server. API Gateway's JWT authorizer returns a bare `401`, which breaks discovery in Claude Desktop and other MCP clients, so the gateway validates Cognito-issued JWTs itself (issuer, audience, expiry, signature via cached JWKS) and enforces scopes per tool.

## Consequences

- API Gateway does routing and throttling only; unauthenticated requests reach Lambda and are rejected there.
- Cognito lacks Dynamic Client Registration, so FastMCP's OAuth proxy fronts it for interactive MCP clients.
