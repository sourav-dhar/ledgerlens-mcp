# Security policy

LedgerLens is a portfolio project that holds only synthetic data, but it is built and operated as if it held real customer data.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through **[GitHub Security Advisories](https://github.com/sourav-dhar/ledgerlens-mcp/security/advisories/new)**, not in public issues. Include the affected component, steps to reproduce and the impact you observed. You can expect an acknowledgement within three working days.

## In scope

- Authentication or authorization bypass on the MCP gateway (token validation, scopes, roles)
- PII exposure that bypasses masking or document-classification controls
- Prompt-injection paths from knowledge-base content into tool behaviour
- Supply-chain weaknesses in the build, images or CI workflows

## Controls already in place

| Area | Control |
|---|---|
| Supply chain | Actions pinned by commit SHA; base images pinned by digest; Dependabot; `pip-audit`; Trivy image scans gate CI |
| Secrets | Gitleaks in pre-commit and CI; secrets only in AWS Secrets Manager; GitHub → AWS via OIDC, no stored keys |
| Runtime | Non-root containers, read-only filesystems, all Linux capabilities dropped |
| Data | PAN tokenised under KMS; Aadhaar never stored in full; row-level security on document classification; append-only audit log |
