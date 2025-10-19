"""add_role_field

Revision ID: 75bb90356bb0
Revises: c999aae537bc
Create Date: 2025-10-18 16:13:00.822254

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '75bb90356bb0'
down_revision: str | Sequence[str] | None = 'c999aae537bc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add role column with default value 'member'
    op.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'member'")

    # Migrate existing users from legacy boolean fields to roles
    # Priority: admin > viewer > bot > member
    op.execute("UPDATE users SET role = 'admin' WHERE admin = 1")
    op.execute("UPDATE users SET role = 'viewer' WHERE viewer = 1 AND admin = 0")
    op.execute("UPDATE users SET role = 'bot' WHERE bot = 1 AND admin = 0 AND viewer = 0")


def downgrade() -> None:
    """Downgrade schema."""
    # Remove role column
    # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
    op.execute("""
        CREATE TABLE users_temp AS
        SELECT username, api_key, stytch_user_id, email, webhook_url, logo,
               viewer, admin, bot, emoji, created_at
        FROM users
    """)

    op.execute("DROP TABLE users")

    op.execute("ALTER TABLE users_temp RENAME TO users")
