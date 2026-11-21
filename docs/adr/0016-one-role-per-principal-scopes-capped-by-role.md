# Every principal acts in exactly one Role, and its token's scopes are capped by that Role

The gateway must decide what a verified access token may do. Cognito puts two answers in it: the `scope` claim, which the app client was allowed to request, and `cognito:groups`, which says which Role the Staff member holds. Neither is enough alone. Scopes describe the application, not the person, so an app client configured with `kyc:pii` would let every user behind it unmask PANs; groups are absent from client-credentials tokens, so service clients (the e2e runner, the synthetic probe, CI agents) would have no Role at all. The gateway therefore gives every principal exactly one Role, a Staff member's from their group and a service client's from configuration keyed by `client_id`, and grants the **intersection** of the token's scopes and the Role's scopes (plan v1.0 §4). A principal with no Role, or more than one, is refused with `forbidden`. The knowledge-base ceiling follows the Role, and is sent to `core-api` only when `kb:read` survives the intersection.

## Considered Options

- **Trust the token's scopes alone**: simplest, and standard OAuth, but it makes the app client's configuration the only guard on PII: one over-broad client exposes every user's role boundary.
- **Derive scopes from the group alone**: ignores what the client application was granted, so a narrow client (a read-only dashboard) would still act with its user's full write scopes.
- **Union the scopes of several groups**: the glossary gives a Staff member exactly one Role; allowing several would make ceilings and audit ambiguous and turn group membership mistakes into privilege escalation.
- **Give role-less principals a default Role** (`demo_readonly`): convenient, but a misconfigured user or client would then silently work, with no signal that it is misconfigured.

## Consequences

- A call needs both a client permitted to request the scope and a Role allowed to use it; `kyc:pii` stays with compliance officers whatever the client is configured with.
- Service clients are registered in gateway configuration (`MACHINE_CLIENT_ROLES`); an unregistered one fails closed until an operator assigns it a Role.
- The audit record's `roles` field always holds one Role.
- `tests/test_auth.py` reads the plan's Scopes and roles table and requires the gateway's table to equal it, so the plan and the code cannot drift apart silently.
