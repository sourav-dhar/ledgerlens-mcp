# OpenAI embeddings, with full-text search as the degraded mode

Document chunks are embedded with OpenAI `text-embedding-3-large` reduced to 1024 dimensions, which keeps HNSW indexes small with little quality loss. This makes an external provider part of the query path, so when it fails or its breaker is open, search runs Postgres full-text only and the response says `degraded: true` rather than failing.

## Considered Options

- **Amazon Titan Text Embeddings v2**: in-Region and IAM-authenticated, but rejected in favour of retrieval quality and owner preference.
- **Cohere Embed v4 on Bedrock**: only reachable through cross-Region inference profiles, which the project's Region policy forbids.
