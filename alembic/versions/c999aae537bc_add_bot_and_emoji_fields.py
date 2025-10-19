"""add_bot_and_emoji_fields

Revision ID: c999aae537bc
Revises: 898318f0d680
Create Date: 2025-10-18 14:10:14.015541

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c999aae537bc"
down_revision: str | Sequence[str] | None = "898318f0d680"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add bot column (default False for existing users)
    op.execute("ALTER TABLE users ADD COLUMN bot INTEGER NOT NULL DEFAULT 0")

    # Add emoji column (nullable for existing users)
    op.execute("ALTER TABLE users ADD COLUMN emoji TEXT")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove bot and emoji columns
    # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
    op.execute("""
        CREATE TABLE users_temp AS
        SELECT username, api_key, stytch_user_id, email, webhook_url, logo, viewer, admin, created_at
        FROM users
    """)

    op.execute("DROP TABLE users")

    op.execute("ALTER TABLE users_temp RENAME TO users")
