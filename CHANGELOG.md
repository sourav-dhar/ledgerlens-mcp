# Changelog

## [0.2.0](https://github.com/sourav-dhar/ledgerlens-mcp/compare/v0.1.0...v0.2.0) (2026-11-12)


### Features

* **core-api:** add FastAPI walking skeleton with health probes ([85e178b](https://github.com/sourav-dhar/ledgerlens-mcp/commit/85e178b9482b48407e1406a8a287ebd4529d885c))
* **mcp-gateway:** add FastMCP server with stateless Streamable HTTP ([a69b495](https://github.com/sourav-dhar/ledgerlens-mcp/commit/a69b495c7305f6a7cd1c14b7e4e2e76f502706b7))
* **screening-sim:** add sanctions screening vendor simulator skeleton ([c1a2e39](https://github.com/sourav-dhar/ledgerlens-mcp/commit/c1a2e39ff5e137c2b5c0b90c9fdc3cdf881d8bf7))


### Bug Fixes

* **docker:** apply Debian security updates to the runtime image ([ebb7ed4](https://github.com/sourav-dhar/ledgerlens-mcp/commit/ebb7ed4229aee946c233295176d815f179029808))


### Documentation

* add AGENTS.md pointing to CLAUDE.md ([90c1464](https://github.com/sourav-dhar/ledgerlens-mcp/commit/90c1464b33249c422cf0e630363ff175612c5eae))
* add CLAUDE.md agent guide ([b109e9e](https://github.com/sourav-dhar/ledgerlens-mcp/commit/b109e9e4bda4c7a589047b3eb2326da732d561dc))
* add domain glossary and architecture decision records ([032f5af](https://github.com/sourav-dhar/ledgerlens-mcp/commit/032f5afaf67da44f8f087d930f1aebea17b428ee))
* add MkDocs Material site ([23eda80](https://github.com/sourav-dhar/ledgerlens-mcp/commit/23eda802cfc85baaf072b0757aa85536fec6020c))
* add security policy, contributing guide and GitHub templates ([8fb92bf](https://github.com/sourav-dhar/ledgerlens-mcp/commit/8fb92bf32e239d3593dc062ebd5bbd90a92d9898))
* **architecture:** add high-level and low-level design ([f6147e0](https://github.com/sourav-dhar/ledgerlens-mcp/commit/f6147e096c4bbaf32e9c4846364d77e9fa96f327))
* **diagrams:** add Excalidraw architecture diagrams with SVG exports ([dd1c126](https://github.com/sourav-dhar/ledgerlens-mcp/commit/dd1c126892e3daaea0b54ee0379e7ee3807c313f))
* **plans:** add versioned discovery, data model and architecture plans ([8de7496](https://github.com/sourav-dhar/ledgerlens-mcp/commit/8de749676802e82c26064a746fd1b41aba723aa2))


### Build System

* add uv workspace with strict lint, type and test tooling ([61d83ed](https://github.com/sourav-dhar/ledgerlens-mcp/commit/61d83ed8b82d38ba258c6b027562b48e1249455a))
* **compose:** add hardened local stack with pgvector ([3fa31f7](https://github.com/sourav-dhar/ledgerlens-mcp/commit/3fa31f7b6e4598f5b0fd647e8d7dfe29aabb7e5f))
* **deps:** add Dependabot for uv, actions and container images ([5dabb17](https://github.com/sourav-dhar/ledgerlens-mcp/commit/5dabb17dfaa789e61f7b23cfe32ec5c3312a00ac))
* **docker:** add multi-stage uv image shared by every service ([0f485fb](https://github.com/sourav-dhar/ledgerlens-mcp/commit/0f485fbf050e851529f1f1f97965a02e2ad653cd))


### Continuous Integration

* add quality, test, security, image and docs pipelines ([f22f654](https://github.com/sourav-dhar/ledgerlens-mcp/commit/f22f6544dbed076f1b0eb328c8ea15773b5dd57a))
* **release:** keep uv.lock and service versions in step with releases ([2b23956](https://github.com/sourav-dhar/ledgerlens-mcp/commit/2b239568d70592a8ea16fb0e3d95ea2c4e03504b))
* **release:** open release PRs with a PAT so CI runs on them ([e67b4d5](https://github.com/sourav-dhar/ledgerlens-mcp/commit/e67b4d524867af4c46acc6b4d300cf4b1a98b675))
