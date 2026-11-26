# Changelog

## [0.3.0](https://github.com/sourav-dhar/ledgerlens-mcp/compare/v0.2.0...v0.3.0) (2026-11-26)


### Features

* **core-api:** accept only requests the gateway signed ([cf39d05](https://github.com/sourav-dhar/ledgerlens-mcp/commit/cf39d05447f9612978b6a60f10c7911f36463e98))
* **core-api:** add Alembic migrations and the foundation revision ([b6a417e](https://github.com/sourav-dhar/ledgerlens-mcp/commit/b6a417eb1ec3da1c3c6b77d780d48e3fca1ad8a5))
* **core-api:** add KYC, risk and operations tables ([3d9a18e](https://github.com/sourav-dhar/ledgerlens-mcp/commit/3d9a18ef108ac414afcf7744ac67490a34696e89))
* **core-api:** add the knowledge base behind row-level security ([24ff28d](https://github.com/sourav-dhar/ledgerlens-mcp/commit/24ff28d38a9616c612ff5676cfa63bcde883490e))
* **core-api:** create core banking and ledger tables ([8c85e5f](https://github.com/sourav-dhar/ledgerlens-mcp/commit/8c85e5fefa297e51739dfbce4430dc7d832c0162))
* **core-api:** enforce balanced, append-only ledger entries ([6de48ac](https://github.com/sourav-dhar/ledgerlens-mcp/commit/6de48ac068a6947dd463d0a966ac4e37d05f0b72))
* **core-api:** enforce status lifecycles in the database ([66b3d4e](https://github.com/sourav-dhar/ledgerlens-mcp/commit/66b3d4e501adee5c45550dcadcbf551654a55089))
* **core-api:** list AML alerts and total spending by month ([e4de23c](https://github.com/sourav-dhar/ledgerlens-mcp/commit/e4de23cb247bbcc4f00270c9e26b5ade7b8fe4a8))
* **core-api:** make the audit write idempotent and mark replays ([c687351](https://github.com/sourav-dhar/ledgerlens-mcp/commit/c68735141e049babdf225d7c62baa848c01322a2))
* **core-api:** raise disputes and flag Transactions idempotently ([accbd3a](https://github.com/sourav-dhar/ledgerlens-mcp/commit/accbd3a3d7d8c217fc2f9e9ca8dbbbbe0802fed7))
* **core-api:** read a Customer's KYC status and document metadata ([a25cb09](https://github.com/sourav-dhar/ledgerlens-mcp/commit/a25cb097d9d8da64682ccf932c02c5089085acb1))
* **core-api:** read Accounts and page through their Transactions ([9b1a553](https://github.com/sourav-dhar/ledgerlens-mcp/commit/9b1a553af24533c09895bc2619175974f155d380))
* **core-api:** reconcile cached balances against the ledger ([f9f6638](https://github.com/sourav-dhar/ledgerlens-mcp/commit/f9f66386907a225472fd37a963205b258067ec44))
* **core-api:** record processed events so consumers apply each one once ([e0c2c39](https://github.com/sourav-dhar/ledgerlens-mcp/commit/e0c2c390b3688e0b90d7e471d866b0af74df38f9))
* **core-api:** run units of work as kosha_app with the caller's context ([1d3a0cf](https://github.com/sourav-dhar/ledgerlens-mcp/commit/1d3a0cf27339730f39981374beddebd5e4b52bb1))
* **core-api:** search Customers and read their profiles ([4ec17d8](https://github.com/sourav-dhar/ledgerlens-mcp/commit/4ec17d88c7b2c062f2f0db82679baa8f6cc5b2df))
* **core-api:** search the knowledge base and record tool calls ([56575b2](https://github.com/sourav-dhar/ledgerlens-mcp/commit/56575b288061083c8fe304803347753fc339fbf6))
* **core-api:** unmask a PAN for kyc:pii and audit it in the same transaction ([5cc2dc8](https://github.com/sourav-dhar/ledgerlens-mcp/commit/5cc2dc842dc8b1b197ddbf097bd70b45de0cb2c6))
* **kosha-datagen:** generate Accounts, cards, VPAs, Beneficiaries and KYC ([7ac755c](https://github.com/sourav-dhar/ledgerlens-mcp/commit/7ac755ce4e0542a6e0802de8eeb7e2adfc04e6cb))
* **kosha-datagen:** generate Customers, Addresses and Merchants ([e9bb136](https://github.com/sourav-dhar/ledgerlens-mcp/commit/e9bb136e1b854d5948a661ddcdf22df3b2b6801a))
* **kosha-datagen:** generate Transactions and a balanced ledger ([b707eab](https://github.com/sourav-dhar/ledgerlens-mcp/commit/b707eab153602bb4a8454295fbcfcb656ebadbc2))
* **kosha-datagen:** load, reconcile and seed with poe seed ([7718eeb](https://github.com/sourav-dhar/ledgerlens-mcp/commit/7718eeb99b18a4ddf5538c4fb518c548fc9dc645))
* **kosha-datagen:** raise AML alerts, disputes and reviews ([63d29e5](https://github.com/sourav-dhar/ledgerlens-mcp/commit/63d29e55f96e47edcd38321ef3c13b48c1594c96))
* **kosha-datagen:** seal synthetic PANs so the local stack can open them ([c13f46f](https://github.com/sourav-dhar/ledgerlens-mcp/commit/c13f46f3c143e0bedbea68f8870dc5e853537e41))
* **kosha-domain:** add prefixed ULID identifiers ([473fad4](https://github.com/sourav-dhar/ledgerlens-mcp/commit/473fad45a3c5a9d29035e825c8f3825ea249886a))
* **kosha-domain:** add status lifecycles checked against the LLD ([a691400](https://github.com/sourav-dhar/ledgerlens-mcp/commit/a691400078ca6baf1009f69b77873029caa2186b))
* **kosha-domain:** add the closed vocabularies the schema stores ([7c6084b](https://github.com/sourav-dhar/ledgerlens-mcp/commit/7c6084b47d2d0e09c86f723b8d50022d0693e23d))
* **kosha-domain:** add the Paise money type with Indian digit grouping ([5609b71](https://github.com/sourav-dhar/ledgerlens-mcp/commit/5609b71fd8c4d2994f1e35e6d9ed7ead0db2ee3b))
* **kosha-domain:** resolve pincodes to states and carry GST state codes ([d5760a0](https://github.com/sourav-dhar/ledgerlens-mcp/commit/d5760a0a67d939c3013f4aee2653dec028a6fd25))
* **kosha-domain:** seal PANs with envelope encryption behind a keyring ([805aacc](https://github.com/sourav-dhar/ledgerlens-mcp/commit/805aacc8d30959b90b4345357a442ac660b48f91))
* **kosha-domain:** share the dispute rules between generator and API ([f351602](https://github.com/sourav-dhar/ledgerlens-mcp/commit/f35160279d23a1a8a2088e1d401ba95309294dc5))
* **kosha-domain:** sign and verify internal requests ([0d09799](https://github.com/sourav-dhar/ledgerlens-mcp/commit/0d09799e824f11eac7e9b818a0267311b1472492))
* **kosha-domain:** validate PAN, IFSC, VPA, RRN, UTR, GSTIN and mobile ([bcf667f](https://github.com/sourav-dhar/ledgerlens-mcp/commit/bcf667f059c2db0caf206d019bf715b49928de2e))
* **mcp-gateway:** authorize every tool call by Role and scope ([12b3721](https://github.com/sourav-dhar/ledgerlens-mcp/commit/12b37219c22f60c8167e254482481dc7b6044c8d))
* **mcp-gateway:** mask own VPAs and withhold device detail ([86a0f67](https://github.com/sourav-dhar/ledgerlens-mcp/commit/86a0f67cfa54061bc0047d6f44aa4defcb8c1166))
* **mcp-gateway:** mask personal data per scope, declared on the field ([3b2dc53](https://github.com/sourav-dhar/ledgerlens-mcp/commit/3b2dc535e10188674950b7bf3df196d0dac43fd1))
* **mcp-gateway:** raise disputes and flag Transactions once the user agrees ([cbb9d41](https://github.com/sourav-dhar/ledgerlens-mcp/commit/cbb9d410de06d8dad8a09762b185095e44350544))
* **mcp-gateway:** read KYC status and documents; reveal a PAN on request ([c921c75](https://github.com/sourav-dhar/ledgerlens-mcp/commit/c921c75ad0a4000a74bd26eec8468cc6bfd7d5ea))
* **mcp-gateway:** resolve the principal, its Role and scopes ([90aabaa](https://github.com/sourav-dhar/ledgerlens-mcp/commit/90aabaa9aae57126bccf9a127ef39404d529be4f))
* **mcp-gateway:** return tool failures as structured error results ([f7348ed](https://github.com/sourav-dhar/ledgerlens-mcp/commit/f7348ed2dfeac30627c14293151ebd1e30550db6))
* **mcp-gateway:** search Customers and read their profiles ([165e038](https://github.com/sourav-dhar/ledgerlens-mcp/commit/165e0385c2f63c7919d73a6794074299813cd85c))
* **mcp-gateway:** search the knowledge base and read Documents ([14ed71a](https://github.com/sourav-dhar/ledgerlens-mcp/commit/14ed71ace0c6be998dea7e1126fe3e16a401fdea))
* **mcp-gateway:** serve accounts, transactions and spending insights ([70310f3](https://github.com/sourav-dhar/ledgerlens-mcp/commit/70310f3eaa9e0004819775b235db6fbf3088d1ba))
* **mcp-gateway:** serve the AML alert queue and alert evidence ([b283b1f](https://github.com/sourav-dhar/ledgerlens-mcp/commit/b283b1ff0ee28c37af2a72c12cc5ec6cac3be771))
* **mcp-gateway:** sign pagination cursors to their query and subject ([df1c7d7](https://github.com/sourav-dhar/ledgerlens-mcp/commit/df1c7d77e9918a4f5a0be020fd0e157baf2496bd))
* **mcp-gateway:** sign, map and retry calls to core-api ([ba35163](https://github.com/sourav-dhar/ledgerlens-mcp/commit/ba35163d5dd91906a1d774709178f8c4efdd43a4))


### Bug Fixes

* **docker:** rebuild the security-patch layer daily despite the cache ([fc950f2](https://github.com/sourav-dhar/ledgerlens-mcp/commit/fc950f2593ebbbf17cebac71e37da733fecbd536))


### Performance

* **kosha-domain:** encode ULIDs five bits at a time ([9a93db4](https://github.com/sourav-dhar/ledgerlens-mcp/commit/9a93db4641260a29faec5673da836b9d03247564))
* **kosha-domain:** encode ULIDs with the C base32 encoder ([05888c1](https://github.com/sourav-dhar/ledgerlens-mcp/commit/05888c18972bedbe853efded138c3be932ef5a68))


### Refactoring

* **core-api:** share the Postgres test container across packages ([30aa4ee](https://github.com/sourav-dhar/ledgerlens-mcp/commit/30aa4eecbee63cc90d25b20a789d91a48b085923))


### Documentation

* add HANDOFF.md and MEMORY.md for phase-per-session work ([6e8bd85](https://github.com/sourav-dhar/ledgerlens-mcp/commit/6e8bd85213da5dc3858c32f1b5487b645b841c79))
* **adr:** confirm writes by elicitation in either protocol era ([eae2bdd](https://github.com/sourav-dhar/ledgerlens-mcp/commit/eae2bddc28144c5911631ee9ace05fc3cab6bd54))
* **adr:** give every principal one Role and cap its scopes by it ([b0d8628](https://github.com/sourav-dhar/ledgerlens-mcp/commit/b0d8628f67f67c26208945426cedf1956c2dae16))
* **adr:** record opening balances and design the data generator ([96b6cd5](https://github.com/sourav-dhar/ledgerlens-mcp/commit/96b6cd5ff97d34af84c6291ed243910d25ee6eac))
* **adr:** reference partitioned transactions with composite keys ([6ee3881](https://github.com/sourav-dhar/ledgerlens-mcp/commit/6ee3881519595487ce9fd65fc667edce2a507a98))
* **architecture:** authenticate before the per-client rate limit ([f48222b](https://github.com/sourav-dhar/ledgerlens-mcp/commit/f48222b152956aedaa788293f75c0fdae5ad662b))
* close P2 and hand off to the MCP gateway ([129e2b9](https://github.com/sourav-dhar/ledgerlens-mcp/commit/129e2b946c949973a32aad2b62a7b4dfbc37120b))
* **core-api:** map the failure matrix to where core-api tests it ([9839239](https://github.com/sourav-dhar/ledgerlens-mcp/commit/983923913333fdf516bd39cd6d6b05a460177398))
* **diagrams:** fix layout defects and inaccurate labels ([0ea14a4](https://github.com/sourav-dhar/ledgerlens-mcp/commit/0ea14a4ac2be25d907bf9caf593313a70aced089))
* drop the done ruleset action from the handoff ([0113dd0](https://github.com/sourav-dhar/ledgerlens-mcp/commit/0113dd0c6c6a3da973bde3d2396a4f71febf96d3))
* fold plan v1.1 into the P3 handoff ([1295163](https://github.com/sourav-dhar/ledgerlens-mcp/commit/129516326a885fa3293f433922b2a44c54786a1e))
* hand off P1a and record the P1b decisions ([90ca166](https://github.com/sourav-dhar/ledgerlens-mcp/commit/90ca166fa5e037a01e7f34f8dc6d6462716d3fd7))
* hand off P1b and brief P1c ([fc67e05](https://github.com/sourav-dhar/ledgerlens-mcp/commit/fc67e0559761d1832d76817078341805f39808e6))
* hand off P1c with the full-volume seed still to verify ([094e96b](https://github.com/sourav-dhar/ledgerlens-mcp/commit/094e96b024348943b1820019a76a43817a22741a))
* hand off P2 after the customer, account and auth slices ([7c914e5](https://github.com/sourav-dhar/ledgerlens-mcp/commit/7c914e5b117eaddb5e1bb97c1be2fc5530e875b6))
* hand P3 over after the gateway foundation ([1272c8a](https://github.com/sourav-dhar/ledgerlens-mcp/commit/1272c8a99cf1cdb6075abed90547749f4df2285e))
* name the payments PR in the handoff ([1244d90](https://github.com/sourav-dhar/ledgerlens-mcp/commit/1244d90d5b836be4c158a220873014258c05c18a))
* note that shared-data collisions need the whole integration suite ([d186664](https://github.com/sourav-dhar/ledgerlens-mcp/commit/d186664b2315bf480bc39e1c475af31c772acf30))
* **plans:** harden the system design before the gateway (v1.1) ([ee1110e](https://github.com/sourav-dhar/ledgerlens-mcp/commit/ee1110e1aae22c7311169d7a83001192de749625))
* point the handoff at the seed run now that P1c is merged ([404a456](https://github.com/sourav-dhar/ledgerlens-mcp/commit/404a4565b9100d93e77dffe8cb5a263104b22674))
* record real-data tests, KYC tools and the PAN reveal decision ([cb3500d](https://github.com/sourav-dhar/ledgerlens-mcp/commit/cb3500d4852453d632cdd6f1e94b148812725a92))
* record the AML-alert tools and hand off to the knowledge tools ([b183c5d](https://github.com/sourav-dhar/ledgerlens-mcp/commit/b183c5d3ed4bf8dd88ae12e27055523cf73842f1))
* record the knowledge tools and hand off to the write tools ([525c83d](https://github.com/sourav-dhar/ledgerlens-mcp/commit/525c83d8b5182a89a873574b036914416ebe38be))
* record the payments tools and the new masking rules ([b52b698](https://github.com/sourav-dhar/ledgerlens-mcp/commit/b52b6987852a2e75b25654fe045631e852e46647))
* record the write tools and hand off to authentication ([ffdb275](https://github.com/sourav-dhar/ledgerlens-mcp/commit/ffdb2758638661bcce7c169a962f20cba5e64e5c))
* refresh the P2 handoff after KYC, writes, AML and insights ([4fd2eea](https://github.com/sourav-dhar/ledgerlens-mcp/commit/4fd2eea65226b14a9a9bf94341094c263e6085e1))
* rewrite README for the completed P0 foundation ([06db279](https://github.com/sourav-dhar/ledgerlens-mcp/commit/06db279dbb66e229233cff5cf10d939a2e9df858))


### Build System

* **compose:** bump pgvector/pgvector ([43a67ec](https://github.com/sourav-dhar/ledgerlens-mcp/commit/43a67ec69b2e94dcffac1cdc9d42ef77c2cbd3a7))
* **core-api:** depend on kosha-domain, Alembic and psycopg ([cd069db](https://github.com/sourav-dhar/ledgerlens-mcp/commit/cd069db3fafe12f4a213b5a3684fca5e7ccda4a6))
* **deps:** bump the python-minor-and-patch group across 1 directory with 5 updates ([85ced3b](https://github.com/sourav-dhar/ledgerlens-mcp/commit/85ced3b3365dc5f4af7b9027d9a9b132464de496))
* **docker:** copy shared packages into service images ([9b2376e](https://github.com/sourav-dhar/ledgerlens-mcp/commit/9b2376e52cebea91a960bc77fc9d5d10244c8b39))
* **kosha-domain:** add the shared domain package to the workspace ([3ce7f5c](https://github.com/sourav-dhar/ledgerlens-mcp/commit/3ce7f5c9c255667a1985cd415cd95e8877feb923))


### Continuous Integration

* **deps:** bump the actions group across 1 directory with 2 updates ([4934ed9](https://github.com/sourav-dhar/ledgerlens-mcp/commit/4934ed9c44a0d12f284e6c2192e28c468125c0bb))
* enforce coverage over unit and integration tests together ([a705c0a](https://github.com/sourav-dhar/ledgerlens-mcp/commit/a705c0ac39be67a102dc72db379e2ab633ff92da))
* parse every Mermaid diagram in the docs build ([f2dceb4](https://github.com/sourav-dhar/ledgerlens-mcp/commit/f2dceb46c800a7e92184b475b327edcafabec448))
* run the integration suite against Postgres ([f4b7856](https://github.com/sourav-dhar/ledgerlens-mcp/commit/f4b78568be82e51470825bab94ffa965fd1cf2ff))
* smoke-test that the gateway image fails closed without identity ([f789065](https://github.com/sourav-dhar/ledgerlens-mcp/commit/f789065e71f7672debf56b4be0c52d23fbc68016))

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
