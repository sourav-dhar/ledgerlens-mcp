# MCP gateway calls the Core Banking API over HTTP

The MCP server (`mcp-gateway`) owns protocol, auth, masking and audit; all domain logic and persistence live in a separate FastAPI service (`core-api`) reached over HTTP. We accept an extra network hop because it mirrors how an MCP layer sits in front of existing bank systems, keeps the domain usable by non-MCP clients, and gives timeouts, retries and circuit breakers a real failure boundary to protect.

## Considered Options

- **Tools call repositories in-process**: fewer moving parts and lower latency, but resilience patterns would guard nothing real, and the domain would be welded to one protocol.
