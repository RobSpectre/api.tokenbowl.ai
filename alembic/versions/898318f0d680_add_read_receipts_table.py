"""add_read_receipts_table

Revision ID: 898318f0d680
Revises: 182ab482e2ea
Create Date: 2025-10-18 12:38:21.496082

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "898318f0d680"
down_revision: str | Sequence[str] | None = "182ab482e2ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS read_receipts (
            message_id TEXT NOT NULL,
            username TEXT NOT NULL,
            read_at TEXT NOT NULL,
            PRIMARY KEY (message_id, username),
            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
            FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
        )
    """)

    # Create index for efficient queries by username
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_read_receipts_username
        ON read_receipts(username)
    """)

    # Create index for efficient queries by message_id
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_read_receipts_message_id
        ON read_receipts(message_id)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS read_receipts")
