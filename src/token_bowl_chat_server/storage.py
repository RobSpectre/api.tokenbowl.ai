"""SQLite storage for users and messages."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional
from uuid import UUID

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
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    api_key TEXT UNIQUE NOT NULL,
                    webhook_url TEXT,
                    logo TEXT,
                    viewer INTEGER NOT NULL DEFAULT 0,
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
                INSERT INTO users (username, api_key, webhook_url, logo, viewer, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user.username,
                    user.api_key,
                    str(user.webhook_url) if user.webhook_url else None,
                    user.logo,
                    1 if user.viewer else 0,
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
                webhook_url=HttpUrl(row["webhook_url"]) if row["webhook_url"] else None,
                logo=row["logo"],
                viewer=bool(row["viewer"]),
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
                webhook_url=HttpUrl(row["webhook_url"]) if row["webhook_url"] else None,
                logo=row["logo"],
                viewer=bool(row["viewer"]),
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
                    webhook_url=HttpUrl(row["webhook_url"]) if row["webhook_url"] else None,
                    logo=row["logo"],
                    viewer=bool(row["viewer"]),
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
                    webhook_url=HttpUrl(row["webhook_url"]) if row["webhook_url"] else None,
                    logo=row["logo"],
                    viewer=bool(row["viewer"]),
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
