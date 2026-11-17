"""Consumer dedupe for at-least-once delivery.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    -- SQS delivers at least once and the outbox relay may publish twice, so each consumer
    -- records the events it has applied in the same transaction as their effect:
    -- INSERT ... ON CONFLICT DO NOTHING, and a conflict means skip. Keyed per consumer, so
    -- two consumers of one event dedupe independently. Kept 30 days, longer than DLQ
    -- retention plus redrive time, by a scheduled purge.
    CREATE TABLE ops.processed_events (
        consumer text NOT NULL,
        event_id text NOT NULL CHECK (kosha.is_id(event_id, 'evt')),
        processed_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (consumer, event_id)
    );
    CREATE INDEX processed_events_age_idx ON ops.processed_events (processed_at);

    GRANT SELECT, INSERT, DELETE ON ops.processed_events TO kosha_app;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE ops.processed_events")
