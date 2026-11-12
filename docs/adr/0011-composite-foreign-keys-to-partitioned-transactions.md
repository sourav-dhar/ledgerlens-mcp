# Rows that reference a Transaction carry its `initiated_at` in a composite foreign key

`core.transactions` is range-partitioned by month on `initiated_at`, and PostgreSQL requires the partition key in every primary key and unique constraint of a partitioned table. Its primary key is therefore `(txn_id, initiated_at)`. Every table that references a Transaction (status history, journal entries, disputes, transaction reviews) stores `txn_initiated_at` beside `txn_id` and declares a composite foreign key to that pair, so referential integrity stays in the database.

## Considered Options

- **Foreign key on `txn_id` alone**: impossible; PostgreSQL cannot enforce uniqueness of `txn_id` across partitions, and a foreign key needs a unique target.
- **No foreign key, integrity checked by the application or a trigger**: keeps child tables narrow, but a trigger-based check is slower than a native key and races under concurrent writes; dispute and ledger rows are exactly where orphans would hurt.
- **An unpartitioned `transaction_ids` lookup table that children reference**: one more write and one more 1.5M-row index per Transaction, to save one column per child row.
- **Not partitioning `core.transactions`**: simplest keys, but date-bounded queries (the default 90-day window of `search_transactions`) lose partition pruning, and old months can no longer be detached and archived.

## Consequences

- `txn_id` is unique by construction (an 80-bit random ULID), not by constraint. Looking a Transaction up by `txn_id` alone probes one index per partition; callers that know `initiated_at` should pass it so the planner prunes.
- Child rows repeat a timestamp. That is 8 bytes per row, and it lets child tables themselves be partitioned later on the same key.
