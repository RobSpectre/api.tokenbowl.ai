"""WebSocket connection management for real-time messaging."""

import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from .auth import validate_api_key
from .models import Message, MessageResponse, User

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for users."""

    def __init__(self) -> None:
        """Initialize connection manager."""
        self.active_connections: dict[str, WebSocket] = {}  # username -> WebSocket

    async def connect(self, websocket: WebSocket, user: User) -> None:
        """Accept a WebSocket connection for a user.

        Args:
            websocket: WebSocket connection
            user: Authenticated user
        """
        await websocket.accept()
        self.active_connections[user.username] = websocket
        logger.info(f"User {user.username} connected via WebSocket")

    def disconnect(self, username: str) -> None:
        """Remove a WebSocket connection.

        Args:
            username: Username to disconnect
        """
        if username in self.active_connections:
            del self.active_connections[username]
            logger.info(f"User {username} disconnected from WebSocket")

    async def send_message(self, username: str, message: Message) -> bool:
        """Send a message to a specific user via WebSocket.

        Args:
            username: Username to send message to
            message: Message to send

        Returns:
            True if message was sent successfully, False otherwise
        """
        websocket = self.active_connections.get(username)
        if not websocket:
            return False

        try:
            message_data = MessageResponse.from_message(message).model_dump()
            await websocket.send_json(message_data)
            logger.debug(f"Sent message to {username} via WebSocket")
            return True
        except Exception as e:
            logger.error(f"Error sending message to {username}: {e}")
            self.disconnect(username)
            return False

    async def broadcast_to_room(
        self, message: Message, exclude_username: Optional[str] = None
    ) -> None:
        """Broadcast a message to all connected users.

        Args:
            message: Message to broadcast
            exclude_username: Username to exclude from broadcast (e.g., the sender)
        """
        disconnected_users = []
        message_data = MessageResponse.from_message(message).model_dump()

        for username, websocket in self.active_connections.items():
            if exclude_username and username == exclude_username:
                continue

            try:
                await websocket.send_json(message_data)
                logger.debug(f"Broadcasted message to {username}")
            except Exception as e:
                logger.error(f"Error broadcasting to {username}: {e}")
                disconnected_users.append(username)

        # Clean up disconnected users
        for username in disconnected_users:
            self.disconnect(username)

    def get_connected_users(self) -> list[str]:
        """Get list of currently connected usernames.

        Returns:
            List of connected usernames
        """
        return list(self.active_connections.keys())

    def is_connected(self, username: str) -> bool:
        """Check if a user is currently connected.

        Args:
            username: Username to check

        Returns:
            True if user is connected, False otherwise
        """
        return username in self.active_connections


# Global connection manager instance
connection_manager = ConnectionManager()


async def websocket_auth(websocket: WebSocket) -> Optional[User]:
    """Authenticate a WebSocket connection.

    Args:
        websocket: WebSocket connection

    Returns:
        Authenticated user or None if authentication fails
    """
    # Try to get API key from query parameters
    api_key = websocket.query_params.get("api_key")

    if not api_key:
        # Try to get from headers
        api_key = websocket.headers.get("x-api-key")

    if not api_key:
        await websocket.close(code=1008, reason="Missing API key")
        return None

    user = validate_api_key(api_key)
    if not user:
        await websocket.close(code=1008, reason="Invalid API key")
        return None

    return user
