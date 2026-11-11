# Idempotency records are written in the same transaction as the business change

Write tools (`raise_dispute`, `flag_transaction_for_review`) require an idempotency key. The key, a hash of the request and the stored response are inserted in the same PostgreSQL transaction as the business rows and the outbox event, so a retried request can never apply twice or return a different answer. A reused key with a different request hash is rejected as a conflict.

## Considered Options

- **Powertools idempotency on DynamoDB**: well-supported, but it lives outside the business transaction, leaving a window where the write commits and the idempotency record does not (or the reverse).
