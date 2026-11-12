# LedgerLens MCP

Production-grade MCP server for **Kosha Financial**, a fictional Indian neobank: FastMCP gateway → FastAPI Core Banking API → PostgreSQL + pgvector, deployed as Lambda container images on AWS. Public portfolio repo: every commit, doc and diagram is read by recruiters, so it ships polished.

Machine- and account-specific context lives in `CLAUDE.local.md` (gitignored). Read it when touching AWS, git identity or the local shell.

## Where the truth lives

- **Plan and phase you are in** → `docs/plans/v1.0-architecture.md` (§9 lists phases and exit criteria). Data model, status lifecycles and SOP corpus → `docs/plans/v0.2-data-model-and-corpus.md`.
- **Component design** → `docs/architecture/hld.md` and `docs/architecture/lld/<component>.md`. Read the component's LLD before changing it; update it in the same change when the design moves.
- **Settled decisions** → `docs/adr/`. Check here before proposing an alternative; a rejected option stays rejected unless a new ADR supersedes it.
- **Domain language** → `GLOSSARY.md`. Use its terms in code, tests, docs and commit messages; its _Avoid_ lists name the synonyms to retire.
- **Commands** → `[tool.poe.tasks]` in `pyproject.toml` (`uv run poe --help`). `uv run poe check` is the gate before every commit.

## How work flows

1. Build test-first with the `tdd` skill: a failing test through the public interface goes **red**, the smallest change turns it green, then refactor. Tools are tested through FastMCP's in-memory `Client`; HTTP through `httpx.ASGITransport`.
2. Each tool ships with its failure matrix (plan §8): auth, scopes, masking per role, bad input, not-found, timeouts, breaker open, rate limit, idempotency.
3. Gates stay green: ruff, pyright **strict at zero errors**, pytest with warnings as errors, 90%+ coverage measured per package.
4. Commit one logical change at a time as Conventional Commits (`feat(mcp-gateway): …`, scopes are service names or `docker`, `compose`, `plans`, `adr`, `ci`). The body says _why_. Push after each green commit.
5. A hard-to-reverse, surprising, traded-off decision gets an ADR (`domain-modeling` skill). A changed plan gets a new version file plus a row in `docs/plans/CHANGELOG.md`; accepted plans are superseded, not rewritten.

## Domain invariants

- Money is integer **paise** in `*_paise` fields; every amount stays an `int` end to end.
- Timestamps are UTC `timestamptz`; IST exists only at the presentation edge.
- Aadhaar is stored only as a vault token plus last 4 digits; PAN only as a KMS-encrypted token plus last 4. Full values reach a caller only with the `kyc:pii` scope.
- IDs are prefixed ULIDs (`cus_`, `acc_`, `txn_`, …).
- Status changes go through the lifecycle tables in plan v0.2 §1a; every transition is recorded in history.
- All data is synthetic; customers and the company are fictional, regulations cited are real.

## Code conventions and gotchas

- Services expose `create_app(settings)` and a `kosha-serve` entry point; settings come from `pydantic-settings` and default `HOST` to loopback (containers set `0.0.0.0`).
- MCP SDK v2 field names are snake_case (`read_only_hint`, `server_info`, `output_schema`); camelCase access raises a deprecation warning, which the test suite treats as an error.
- Async tests use AnyIO's plugin via `pytestmark = pytest.mark.anyio`: it keeps fixture setup and teardown in one task, which FastMCP's task-group lifespan requires.
- `docker/Dockerfile` keeps the virtualenv layer reproducible so code-only rebuilds take seconds. When a shared library is added under `packages/`, copy its source in **both** the builder and runtime stages, as is done for `services/${SERVICE}`.
- GitHub Actions are pinned by commit SHA with a `# vX.Y.Z` comment; base images by tag and digest. Dependabot bumps both.
- Public files carry no account IDs, emails or machine paths; those belong in `CLAUDE.local.md`.

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance for the new AWS experience

This user has signed up for the new AWS experience. This experience lets you sign into AWS using a social provider and requires the following additional context.

Where this guidance conflicts with the project's own instructions, the project's instructions take precedence.

## Context

### Terminology:

- Say "project" instead of "account" — a project contains an AWS account and settings for sharing with other collaborators
- Say "team member" instead of "IAM user" — users are invited by email, not created or federated in IAM
- Say "AWS Settings" when referring to management tasks at [settings.aws.com](https://settings.aws.com/) (project management, billing, team members, spend limits). Users view their actual AWS resources in the AWS Management Console.
- Say "selected Region" when referring to the user's Region — not "home Region"
- The user has a managed IAM experience. This includes a managed service control policies (SCP) and resource control policies (RCP) that govern the use of AWS. They will still need to use IAM to create policies to let services work with each other. If there are questions about the SCPs or RCPs, go to the documentation at https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html

### Constraints:

- All projects share a single AWS Region determined by the user's contact address. Resources cannot be created in other Regions
- When developing:
  - MUST create all Regional resources in the project's assigned Region
  - You CAN create AWS WAF and Cloudwatch Logs resources in us-east-1 when there are global resources (like a global WAF instance) that require a connection to dependencies in us-east-1. You should not use these for any other reason, because resources in the selected Region will provide lower cost (due to no cross-Region traffic), increased availability (due to no cross-Region traffic), and easier manageability (due to not needing to look in another Region). When you need to do an inventory of resources, you need to look in both the selected Region and us-east-1 for Cloudwatch Logs or WAF resources.
  - MUST NOT attempt to create Lambda, API Gateway, or other Regional resources in any other Region
  - MUST direct users to confirm their Region in AWS Settings > View all projects > Overview > Additional Info > Region. If the user cannot confirm their Region, check in ~/.aws/config
  - MUST NOT use Lambda@Edge — excluded from both Lambda and CloudFront
  - MUST NOT use CloudFormation StackSets — no multi-account or multi-Region deployments
  - MUST NOT attempt cross-Region actions — no cross-Region replication for DynamoDB/S3/RDS, no multi-Region KMS keys
  - MUST NOT use Route 53 cross-Region routing — geolocation, latency-based, and failover routing policies are not available
  - CloudFront is a global service and its actions ARE allowed in `us-east-1`. A user can create a CloudFront distribution pointing to their project-region Lambda function URL or API Gateway. However, Lambda and API Gateway themselves MUST NOT be created in `us-east-1` — they must be in the project Region.
  - Reduced availability in `eu-north-1` specifically: Amazon Rekognition, Amazon Textract, Amazon Personalize, AWS App Runner are not available in that Region.
- IAM permissions for human access are managed by AWS. Don't assign roles to team members unless absolutely necessary
- The user may have a spend limit if they are on the paid plan. The limit that pauses their project if it's exceeded. If resources suddenly become inaccessible, ask if they have a spend limit configured. Only project owners can modify a spend limit.
- When developing:
  - MUST ask about spend limit status if the user reports sudden "Access Denied" errors on operations that previously worked
  - MUST direct users to check spend status in AWS Settings > Billing
  - MUST check if a user has upgraded their account to the paid plan
  - MUST ask the user if they want to clean up the successfully created resources or keep them to reduce cost
- The user sets up billing, creates spend limits, and retrieves and pays invoices in AWS Settings. The user creates budgets and optimizes their costs in the AWS Billing and Cost Management console
- Not all AWS services are available. If a service isn't working, do the following:
  1. Run the command `aws freetier get-account-plan-state`
  2. If accountPlanType": "FREE", check the [Free Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-free-tier) next,
  3. If accountPlanType": "PAID", check the [Paid Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-paid-plan).
  4. If neither list shows the service, check the [Not supported for this experience list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#unsupported-services). The user will need to activate advanced features to access this service.
- Users can activate advanced AWS services and capabilities for their account.
- For any AWS task or question — building, configuring, migrating, debugging, or operating a service, writing SDK code, authoring CDK/CloudFormation, or answering how a service works — first call `aws___search_documentation` with topic `agent_skills` and load the matching skill with `aws___retrieve_skill`. Do this even when you believe you know the answer: skills carry current service behavior that your training may not. Prefer the skill's guidance over general knowledge. Skip it only for work that does not involve AWS.

### Help level

- help_level (required): LOW, MEDIUM, or HIGH. While a user is building, you MUST ask the user: "How much guidance would you like from me? Low (I only flag security risks), medium (I ask a couple of clarifying questions if something seems off), or high (I explain what I'm doing, suggest alternatives, and flag best practices)."

You CAN update this rule file to save a user's help_level.

Constraints for each level:

**LOW:**

- MUST follow all constraints in this context file
- MUST execute the user’s request without modification
- MUST NOT ask clarifying questions unless the action would create a security vulnerability
- MUST NOT suggest alternatives or improvements

**MEDIUM:**

- MUST execute the user's request
- MAY ask up to two clarifying questions per task if the request has an ambiguity or a potential issue
- MUST NOT repeat a question or suggestion the user has already dismissed
- MUST NOT explain trade-offs or alternatives unless the user asks

**HIGH:**

- MUST explain what each step does and why before executing it
- MUST suggest alternatives when a better approach exists
- MUST flag best practices and explain trade-offs
- MUST still execute the user's choice if they disagree with a suggestion
<!-- END AWS Agent Toolkit rules -->
