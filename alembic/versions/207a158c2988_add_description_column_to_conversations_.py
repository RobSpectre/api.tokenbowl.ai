"""Add description column to conversations table

Revision ID: 207a158c2988
Revises: 4e6bb17001fc
Create Date: 2025-10-28 16:44:45.599020

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "207a158c2988"
down_revision: str | Sequence[str] | None = "4e6bb17001fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add description column to conversations table
    op.execute("ALTER TABLE conversations ADD COLUMN description TEXT")


def downgrade() -> None:
    """Downgrade schema."""
    # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
    op.execute("""
        CREATE TABLE conversations_backup (
            id TEXT PRIMARY KEY,
            title TEXT,
            message_ids TEXT NOT NULL,
            created_by_username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (created_by_username) REFERENCES users(username) ON DELETE CASCADE
        )
    """)
    op.execute("""
        INSERT INTO conversations_backup (id, title, message_ids, created_by_username, created_at)
        SELECT id, title, message_ids, created_by_username, created_at FROM conversations
    """)
    op.execute("DROP TABLE conversations")
    op.execute("ALTER TABLE conversations_backup RENAME TO conversations")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversations_created_by
        ON conversations(created_by_username)
    """)
