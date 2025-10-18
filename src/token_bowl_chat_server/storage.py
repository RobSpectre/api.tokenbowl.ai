"""SQLite storage for users and messages."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional
from uuid import UUID

from alembic import command
from alembic.config import Config
from pydantic import HttpUrl

from .models import Message, MessageType, User


class ChatStorage:
    """SQLite storage for the chat server."""

    def __init__(self, db_path: str = "chat.db", message_history_limit: int = 100) -> None:
        """Initialize storage.

        Args:
            db_path: Path to SQLite database file (use ':memory:' for in-memory)
            message_history_limit: Maximum number of messages to keep in history
        """
        self.db_path = db_path
        self.message_history_limit = message_history_limit

        # Keep persistent connection for in-memory databases
        self._conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            # check_same_thread=False allows connection to be used across threads (safe for in-memory DB)
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema using Alembic migrations."""
        # Skip migrations for in-memory databases in tests
        if self.db_path == ":memory:":
            # For in-memory databases, create schema directly for speed
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Create users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        api_key TEXT UNIQUE NOT NULL,
                        stytch_user_id TEXT UNIQUE,
                        email TEXT,
                        webhook_url TEXT,
                        logo TEXT,
                        viewer INTEGER NOT NULL DEFAULT 0,
                        admin INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL
                    )
                """)

                # Create messages table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
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
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_timestamp
                    ON messages(timestamp)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_to_username
                    ON messages(to_username)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_from_username
                    ON messages(from_username)
                """)

                conn.commit()
        else:
            # For file-based databases, use Alembic migrations
            self._run_migrations()

    def _run_migrations(self) -> None:
        """Run Alembic migrations to upgrade database to latest version."""
        # Get the path to alembic.ini
        alembic_ini_path = Path(__file__).parent.parent.parent / "alembic.ini"

        # Create Alembic config
        alembic_cfg = Config(str(alembic_ini_path))

        # Override database URL to use the configured db_path
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

        # Run migrations to latest version
        command.upgrade(alembic_cfg, "head")

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get database connection context manager."""
        if self._conn is not None:
            # Use persistent connection for in-memory databases
            yield self._conn
        else:
            # Create temporary connection for file-based databases
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def __del__(self) -> None:
        """Close persistent connection on deletion."""
        if self._conn is not None:
            self._conn.close()

    def add_user(self, user: User) -> None:
        """Add a user to storage.

        Args:
            user: User to add

        Raises:
            ValueError: If username or API key already exists
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check if username exists
            cursor.execute("SELECT username FROM users WHERE username = ?", (user.username,))
            if cursor.fetchone():
                raise ValueError(f"Username {user.username} already exists")

            # Check if API key exists
            cursor.execute("SELECT api_key FROM users WHERE api_key = ?", (user.api_key,))
            if cursor.fetchone():
                raise ValueError("API key already exists")

            # Insert user
            cursor.execute(
                """
                INSERT INTO users (username, api_key, stytch_user_id, email, webhook_url, logo, viewer, admin, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.username,
                    user.api_key,
                    user.stytch_user_id,
                    user.email,
                    str(user.webhook_url) if user.webhook_url else None,
                    user.logo,
                    1 if user.viewer else 0,
                    1 if user.admin else 0,
                    user.created_at.isoformat(),
                ),
            )
            conn.commit()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username.

        Args:
            username: Username to look up

        Returns:
            User if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()

            if not row:
                return None

            return User(
                username=row["username"],
                api_key=row["api_key"],
                stytch_user_id=row["stytch_user_id"],
                email=row["email"],
                webhook_url=HttpUrl(row["webhook_url"]) if row["webhook_url"] else None,
                logo=row["logo"],
                viewer=bool(row["viewer"]),
                admin=bool(row["admin"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        """Get user by API key.

        Args:
            api_key: API key to look up

        Returns:
            User if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE api_key = ?", (api_key,))
            row = cursor.fetchone()

            if not row:
                return None

            return User(
                username=row["username"],
                api_key=row["api_key"],
                stytch_user_id=row["stytch_user_id"],
                email=row["email"],
                webhook_url=HttpUrl(row["webhook_url"]) if row["webhook_url"] else None,
                logo=row["logo"],
                viewer=bool(row["viewer"]),
                admin=bool(row["admin"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    def get_user_by_stytch_id(self, stytch_user_id: str) -> Optional[User]:
        """Get user by Stytch user ID.

        Args:
            stytch_user_id: Stytch user ID to look up

        Returns:
            User if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE stytch_user_id = ?", (stytch_user_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return User(
                username=row["username"],
                api_key=row["api_key"],
                stytch_user_id=row["stytch_user_id"],
                email=row["email"],
                webhook_url=HttpUrl(row["webhook_url"]) if row["webhook_url"] else None,
                logo=row["logo"],
                viewer=bool(row["viewer"]),
                admin=bool(row["admin"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    def update_user_logo(self, username: str, logo: Optional[str]) -> bool:
        """Update a user's logo.

        Args:
            username: Username to update
            logo: New logo filename (must be in AVAILABLE_LOGOS or None)

        Returns:
            True if user was updated, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET logo = ? WHERE username = ?", (logo, username))
            conn.commit()
            return cursor.rowcount > 0

    def update_user_webhook(self, username: str, webhook_url: Optional[str]) -> bool:
        """Update a user's webhook URL.

        Args:
            username: Username to update
            webhook_url: New webhook URL (or None to clear)

        Returns:
            True if user was updated, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET webhook_url = ? WHERE username = ?", (webhook_url, username))
            conn.commit()
            return cursor.rowcount > 0

    def update_user_api_key(self, username: str, new_api_key: str) -> bool:
        """Update a user's API key.

        Args:
            username: Username to update
            new_api_key: New API key

        Returns:
            True if user was updated, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET api_key = ? WHERE username = ?", (new_api_key, username))
            conn.commit()
            return cursor.rowcount > 0

    def update_username(self, old_username: str, new_username: str) -> None:
        """Update a user's username.

        Args:
            old_username: Current username
            new_username: New username

        Raises:
            ValueError: If new username already exists or user not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check if old user exists
            cursor.execute("SELECT username FROM users WHERE username = ?", (old_username,))
            if not cursor.fetchone():
                raise ValueError(f"User {old_username} not found")

            # Check if new username already exists
            cursor.execute("SELECT username FROM users WHERE username = ?", (new_username,))
            if cursor.fetchone():
                raise ValueError(f"Username {new_username} already exists")

            # Update username in users table
            cursor.execute("UPDATE users SET username = ? WHERE username = ?", (new_username, old_username))

            # Update username in messages table (both from and to)
            cursor.execute("UPDATE messages SET from_username = ? WHERE from_username = ?", (new_username, old_username))
            cursor.execute("UPDATE messages SET to_username = ? WHERE to_username = ?", (new_username, old_username))

            conn.commit()

    def add_message(self, message: Message) -> None:
        """Add a message to storage.

        Args:
            message: Message to add
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Insert message
            cursor.execute(
                """
                INSERT INTO messages (id, from_username, to_username, content, message_type, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(message.id),
                    message.from_username,
                    message.to_username,
                    message.content,
                    message.message_type.value,
                    message.timestamp.isoformat(),
                ),
            )

            # Trim message history if needed
            cursor.execute("SELECT COUNT(*) as count FROM messages")
            count = cursor.fetchone()["count"]

            if count > self.message_history_limit:
                # Delete oldest messages
                delete_count = count - self.message_history_limit
                cursor.execute(
                    """
                    DELETE FROM messages
                    WHERE id IN (
                        SELECT id FROM messages
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )
                    """,
                    (delete_count,),
                )

            conn.commit()

    def get_recent_messages(
        self, limit: int = 50, offset: int = 0, since: Optional[datetime] = None
    ) -> list[Message]:
        """Get recent room messages with pagination support.

        Args:
            limit: Maximum number of messages to return
            offset: Number of messages to skip from the start
            since: Only return messages after this timestamp

        Returns:
            List of recent messages
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM messages WHERE to_username IS NULL"
            params: list = []

            if since:
                query += " AND timestamp > ?"
                params.append(since.isoformat())

            query += " ORDER BY timestamp ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [self._row_to_message(row) for row in rows]

    def get_direct_messages(
        self, username: str, limit: int = 50, offset: int = 0, since: Optional[datetime] = None
    ) -> list[Message]:
        """Get direct messages for a user with pagination support.

        Args:
            username: Username to get messages for
            limit: Maximum number of messages to return
            offset: Number of messages to skip from the start
            since: Only return messages after this timestamp

        Returns:
            List of direct messages
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT * FROM messages
                WHERE to_username IS NOT NULL
                AND (to_username = ? OR from_username = ?)
            """
            params: list = [username, username]

            if since:
                query += " AND timestamp > ?"
                params.append(since.isoformat())

            query += " ORDER BY timestamp ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [self._row_to_message(row) for row in rows]

    def get_room_messages_count(self, since: Optional[datetime] = None) -> int:
        """Get total count of room messages.

        Args:
            since: Only count messages after this timestamp

        Returns:
            Total count of room messages
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT COUNT(*) as count FROM messages WHERE to_username IS NULL"
            params: list = []

            if since:
                query += " AND timestamp > ?"
                params.append(since.isoformat())

            cursor.execute(query, params)
            return cursor.fetchone()["count"]

    def get_direct_messages_count(self, username: str, since: Optional[datetime] = None) -> int:
        """Get total count of direct messages for a user.

        Args:
            username: Username to count messages for
            since: Only count messages after this timestamp

        Returns:
            Total count of direct messages
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT COUNT(*) as count FROM messages
                WHERE to_username IS NOT NULL
                AND (to_username = ? OR from_username = ?)
            """
            params: list = [username, username]

            if since:
                query += " AND timestamp > ?"
                params.append(since.isoformat())

            cursor.execute(query, params)
            return cursor.fetchone()["count"]

    def get_all_users(self) -> list[User]:
        """Get all registered users.

        Returns:
            List of all users
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY created_at ASC")
            rows = cursor.fetchall()

            return [
                User(
                    username=row["username"],
                    api_key=row["api_key"],
                    stytch_user_id=row["stytch_user_id"],
                    email=row["email"],
                    webhook_url=HttpUrl(row["webhook_url"]) if row["webhook_url"] else None,
                    logo=row["logo"],
                    viewer=bool(row["viewer"]),
                    admin=bool(row["admin"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    def get_chat_users(self) -> list[User]:
        """Get all chat users (non-viewer users).

        Returns:
            List of chat users
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE viewer = 0 ORDER BY created_at ASC")
            rows = cursor.fetchall()

            return [
                User(
                    username=row["username"],
                    api_key=row["api_key"],
                    stytch_user_id=row["stytch_user_id"],
                    email=row["email"],
                    webhook_url=HttpUrl(row["webhook_url"]) if row["webhook_url"] else None,
                    logo=row["logo"],
                    viewer=bool(row["viewer"]),
                    admin=bool(row["admin"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    def delete_user(self, username: str) -> bool:
        """Delete a user.

        Args:
            username: Username to delete

        Returns:
            True if user was deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
            return cursor.rowcount > 0

    def admin_update_user(
        self,
        username: str,
        email: Optional[str] = None,
        webhook_url: Optional[str] = None,
        logo: Optional[str] = None,
        viewer: Optional[bool] = None,
        admin: Optional[bool] = None,
    ) -> bool:
        """Admin-only: Update any user's profile fields.

        Args:
            username: Username to update
            email: New email (or None to skip)
            webhook_url: New webhook URL (or None to skip)
            logo: New logo (or None to skip)
            viewer: New viewer status (or None to skip)
            admin: New admin status (or None to skip)

        Returns:
            True if user was updated, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build update query dynamically
            updates = []
            params = []

            if email is not None:
                updates.append("email = ?")
                params.append(email)
            if webhook_url is not None:
                updates.append("webhook_url = ?")
                params.append(webhook_url)
            if logo is not None:
                updates.append("logo = ?")
                params.append(logo)
            if viewer is not None:
                updates.append("viewer = ?")
                params.append(1 if viewer else 0)
            if admin is not None:
                updates.append("admin = ?")
                params.append(1 if admin else 0)

            if not updates:
                return False

            params.append(username)
            query = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"

            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

    def get_message_by_id(self, message_id: str) -> Optional[Message]:
        """Get a message by its ID.

        Args:
            message_id: Message ID to look up

        Returns:
            Message if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_message(row)

    def delete_message(self, message_id: str) -> bool:
        """Delete a message by ID.

        Args:
            message_id: Message ID to delete

        Returns:
            True if message was deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE id = ?", (message_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_message_content(self, message_id: str, content: str) -> bool:
        """Update message content.

        Args:
            message_id: Message ID to update
            content: New content

        Returns:
            True if message was updated, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE messages SET content = ? WHERE id = ?",
                (content, message_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_message(self, row: sqlite3.Row) -> Message:
        """Convert database row to Message object.

        Args:
            row: Database row

        Returns:
            Message object
        """
        return Message(
            id=UUID(row["id"]),
            from_username=row["from_username"],
            to_username=row["to_username"],
            content=row["content"],
            message_type=MessageType(row["message_type"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )


# Global storage instance
storage = ChatStorage()
