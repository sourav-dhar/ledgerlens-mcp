# Balances older than the ledger are brought forward against an `opening_balances` GL account

The ledger starts on the first day of the 18-month Transaction window, but some Accounts are older: an inoperative Account needs 24 months without Customer activity, and Re-KYC falls due only on profiles two to ten years old. Each such Account starts with one journal entry that has no Transaction: the Account's sub-ledger of `customer_deposits` is credited with its balance on go-live day, and a dedicated `opening_balances` GL account is debited by the same amount. Revision 0007 adds the GL value; `kosha-domain`'s `GlAccount` carries it, and the enum parity test keeps the two in step.

## Considered Options

- **Post the contra to `suspense`**: no schema change, but suspense is where unexplained differences wait to be cleared. Crores of uncleared suspense reads, to anyone who knows a bank's books, as a ledger that does not reconcile.
- **Open every Account inside the window, starting at zero**: no contra at all, but no inoperative Accounts, no Re-KYC-due or overdue profiles and no long-standing relationships, which are exactly the cases the support and compliance SOPs are written for.
- **Generate the years before the window as Transactions too**: an honest history, at roughly three times the rows and load time, for months no tool or demo queries.

## Consequences

- `ledger.account_reconciliation` compares cached balances with Postings, opening entries included, so it holds for old and new Accounts alike.
- The `opening_balances` balance equals the negated sum of every brought-forward balance; the ledger as a whole still sums to zero.
- Postgres cannot drop an enum value, so revision 0007's downgrade rebuilds `ledger.gl_account` and the Postings CHECK typed by it, and fails while any Posting uses the value.
