"""initial_schema

Revision ID: 369c2ed889c0
Revises:
Create Date: 2025-10-17 17:37:18.567890

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "369c2ed889c0"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create users table
    op.execute("""
        CREATE TABLE users (
            username TEXT PRIMARY KEY,
            api_key TEXT UNIQUE NOT NULL,
            stytch_user_id TEXT UNIQUE,
            email TEXT,
            webhook_url TEXT,
            logo TEXT,
            viewer INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # Create messages table
    op.execute("""
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            from_username TEXT NOT NULL,
            to_username TEXT,
            content TEXT NOT NULL,
            message_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (from_username) REFERENCES users(username)
        )
    """)

    # Create indexes for better query performance
    op.execute("""
        CREATE INDEX idx_messages_timestamp ON messages(timestamp)
    """)
    op.execute("""
        CREATE INDEX idx_messages_to_username ON messages(to_username)
    """)
    op.execute("""
        CREATE INDEX idx_messages_from_username ON messages(from_username)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_messages_from_username")
    op.execute("DROP INDEX IF EXISTS idx_messages_to_username")
    op.execute("DROP INDEX IF EXISTS idx_messages_timestamp")

    # Drop tables
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS users")
