"""add_admin_field_to_users

Revision ID: 182ab482e2ea
Revises: 369c2ed889c0
Create Date: 2025-10-17 17:48:32.215230

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '182ab482e2ea'
down_revision: str | Sequence[str] | None = '369c2ed889c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add admin column to users table
    op.execute("""
        ALTER TABLE users ADD COLUMN admin INTEGER NOT NULL DEFAULT 0
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
    # For simplicity in development, we'll keep it simple
    op.execute("""
        CREATE TABLE users_new (
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
    op.execute("""
        INSERT INTO users_new (username, api_key, stytch_user_id, email, webhook_url, logo, viewer, created_at)
        SELECT username, api_key, stytch_user_id, email, webhook_url, logo, viewer, created_at
        FROM users
    """)
    op.execute("DROP TABLE users")
    op.execute("ALTER TABLE users_new RENAME TO users")
