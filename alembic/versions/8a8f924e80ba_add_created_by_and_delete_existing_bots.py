"""add_created_by_and_delete_existing_bots

Revision ID: 8a8f924e80ba
Revises: 75bb90356bb0
Create Date: 2025-10-18 16:28:41.588674

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8a8f924e80ba'
down_revision: str | Sequence[str] | None = '75bb90356bb0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Delete all existing bots (we're moving to owner-based bot management)
    op.execute("DELETE FROM users WHERE role = 'bot'")

    # Add created_by column (NULL for human users, set for bots)
    op.execute("ALTER TABLE users ADD COLUMN created_by TEXT")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove created_by column
    # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
    op.execute("""
        CREATE TABLE users_temp AS
        SELECT username, api_key, stytch_user_id, email, webhook_url, logo,
               role, viewer, admin, bot, emoji, created_at
        FROM users
    """)

    op.execute("DROP TABLE users")

    op.execute("ALTER TABLE users_temp RENAME TO users")
