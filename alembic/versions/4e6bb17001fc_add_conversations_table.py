"""Add conversations table

Revision ID: 4e6bb17001fc
Revises: ad13e5cd9cce
Create Date: 2025-10-28 15:58:32.934690

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e6bb17001fc"
down_revision: str | Sequence[str] | None = "ad13e5cd9cce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            message_ids TEXT NOT NULL,
            created_by_username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (created_by_username) REFERENCES users(username) ON DELETE CASCADE
        )
    """)

    # Create index for efficient queries by creator
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversations_created_by
        ON conversations(created_by_username)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS conversations")
