# Circuit breakers are per instance, with a shared force-open override

Each Lambda execution environment keeps its own circuit breaker per downstream dependency in memory. Sharing breaker state through a datastore would add a network call to every request and a new failure mode to the thing meant to contain failures. Instances learn independently within a few calls; operators can force a breaker open fleet-wide through a DynamoDB flag that instances poll at most every few seconds.

## Considered Options

- **Breaker state in DynamoDB or Redis on every call**: globally consistent, but slower and itself a dependency that can fail.
