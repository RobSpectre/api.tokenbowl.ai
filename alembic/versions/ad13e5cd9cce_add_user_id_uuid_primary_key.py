"""add_user_id_uuid_primary_key

Revision ID: ad13e5cd9cce
Revises: 8a8f924e80ba
Create Date: 2025-10-19 11:57:16.462696

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "ad13e5cd9cce"
down_revision: str | Sequence[str] | None = "8a8f924e80ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    from alembic import op

    # Note: SQLite doesn't support ALTER TABLE to change primary key directly.
    # We need to create a new table and copy data.

    # Step 1: Create new users table with id as primary key
    op.execute("""
        CREATE TABLE users_new (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            stytch_user_id TEXT UNIQUE,
            email TEXT,
            webhook_url TEXT,
            logo TEXT,
            role TEXT NOT NULL DEFAULT 'member',
            created_by TEXT,
            viewer INTEGER NOT NULL DEFAULT 0,
            admin INTEGER NOT NULL DEFAULT 0,
            bot INTEGER NOT NULL DEFAULT 0,
            emoji TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users_new(id)
        )
    """)

    # Step 2: Copy data from old table to new table, generating UUIDs
    op.execute("""
        INSERT INTO users_new (id, username, api_key, stytch_user_id, email, webhook_url, logo, role, created_by, viewer, admin, bot, emoji, created_at)
        SELECT
            lower(hex(randomblob(16))),  -- Generate UUID-like string
            username,
            api_key,
            stytch_user_id,
            email,
            webhook_url,
            logo,
            role,
            NULL,  -- created_by will be fixed later
            viewer,
            admin,
            bot,
            emoji,
            created_at
        FROM users
    """)

    # Step 3: Drop old table
    op.execute("DROP TABLE users")

    # Step 4: Rename new table
    op.execute("ALTER TABLE users_new RENAME TO users")


def downgrade() -> None:
    """Downgrade schema."""
    from alembic import op

    # Create old table structure with username as primary key
    op.execute("""
        CREATE TABLE users_old (
            username TEXT PRIMARY KEY,
            api_key TEXT UNIQUE NOT NULL,
            stytch_user_id TEXT UNIQUE,
            email TEXT,
            webhook_url TEXT,
            logo TEXT,
            role TEXT NOT NULL DEFAULT 'member',
            created_by TEXT,
            viewer INTEGER NOT NULL DEFAULT 0,
            admin INTEGER NOT NULL DEFAULT 0,
            bot INTEGER NOT NULL DEFAULT 0,
            emoji TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Copy data back
    op.execute("""
        INSERT INTO users_old (username, api_key, stytch_user_id, email, webhook_url, logo, role, created_by, viewer, admin, bot, emoji, created_at)
        SELECT username, api_key, stytch_user_id, email, webhook_url, logo, role, created_by, viewer, admin, bot, emoji, created_at
        FROM users
    """)

    # Drop new table
    op.execute("DROP TABLE users")

    # Rename old table
    op.execute("ALTER TABLE users_old RENAME TO users")
