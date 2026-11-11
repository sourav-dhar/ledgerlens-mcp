# A NAT instance, not a NAT Gateway, provides egress

Lambdas run in private subnets to reach RDS, but still need outbound internet for OpenAI and Cognito JWKS. A managed NAT Gateway costs about $33/month before data; a `t4g.nano` NAT instance costs about $7 including its public IPv4. S3 and DynamoDB use free gateway endpoints so their traffic never touches the NAT.

## Consequences

The NAT instance is a single point of failure for egress. Failure degrades gracefully by design: knowledge search falls back to full-text only and token validation uses cached JWKS. Production would use a NAT Gateway per AZ.
