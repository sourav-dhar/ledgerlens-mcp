# PANs are envelope-encrypted behind a keyring, with a local keyring standing in for KMS until P6

A PAN is stored as a token, never in clear, and only the `kyc:pii` scope may see it whole. Each PAN is sealed with its own AES-256-GCM data key; the data key is wrapped by a `Keyring` (`kosha_domain.vault`), and both layers bind the Customer's ID as authenticated data, so a token copied onto another Customer cannot be opened. In AWS the keyring is KMS (`GenerateDataKey` and `Decrypt` with an encryption context), as LLD security §4 already describes. Until KMS is deployed in P6, a `LocalKeyring` wraps data keys under a key derived from a passphrase, with the same token format (`kms:v1:<wrapped key>.<nonce>.<ciphertext>`). The generator seals every synthetic PAN this way, drawing the randomness from its seeded generator so datasets stay reproducible, and `GET /v1/customers/{id}/kyc/pan` opens it and writes an `ops.audit_log` record (`pii_unmasked`) in the same transaction.

## Considered Options

- **Defer unmasking to P6**: P2 would close sooner, but the `kyc:pii` path, the one place a full PAN leaves the database, would be untested until deployment, and the generator would keep writing tokens nothing can open.
- **Fake the decrypt (store the PAN reversibly encoded)**: trivially simple, but it would test nothing about binding a token to its Customer and would teach the wrong shape to anyone reading the code.
- **LocalStack KMS**: the real API locally, at the cost of another container on a machine already short of memory, for every test run that touches a PAN.

## Consequences

- `kosha-domain` gains its first dependency, `cryptography`, because the generator and `core-api` must agree on the format byte for byte.
- `LocalKeyring` derives its key with a plain SHA-256 of the passphrase: fine for synthetic data, wrong for real secrets. Deployed environments must use the KMS keyring, and data seeded locally cannot be read by it; seeding RDS (P6) must seal PANs under KMS.
- Every unmasking is audited by `core-api` itself, inside the transaction that read the token, so a PAN is never returned without a record even when the gateway's own audit write fails. A token that will not open is a defect (`500`) and leaves no record, because nothing was revealed.
