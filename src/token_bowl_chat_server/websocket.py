"""WebSocket connection management for real-time messaging."""

import logging

from fastapi import WebSocket

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
        client_host = websocket.client.host if websocket.client else "unknown"
        logger.info(f"WebSocket CONNECTED - user: {user.username}, client: {client_host}")

    def disconnect(self, username: str) -> None:
        """Remove a WebSocket connection.

        Args:
            username: Username to disconnect
        """
        if username in self.active_connections:
            del self.active_connections[username]
            logger.info(f"WebSocket DISCONNECTED - user: {username}")

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
            # Fetch sender user info for display
            from .storage import storage

            from_user = storage.get_user_by_username(message.from_username)
            message_data = MessageResponse.from_message(message, from_user=from_user).model_dump()
            await websocket.send_json(message_data)
            logger.debug(f"Sent message to {username} via WebSocket")
            return True
        except Exception as e:
            logger.error(f"Error sending message to {username}: {e}")
            self.disconnect(username)
            return False

    async def send_notification(self, username: str, notification: dict) -> bool:
        """Send a notification to a specific user via WebSocket.

        Args:
            username: Username to send notification to
            notification: Notification data to send

        Returns:
            True if notification was sent successfully, False otherwise
        """
        websocket = self.active_connections.get(username)
        if not websocket:
            return False

        try:
            await websocket.send_json(notification)
            logger.debug(f"Sent notification to {username} via WebSocket")
            return True
        except Exception as e:
            logger.error(f"Error sending notification to {username}: {e}")
            self.disconnect(username)
            return False

    async def broadcast_to_room(
        self, message: Message, exclude_username: str | None = None
    ) -> None:
        """Broadcast a message to all connected users.

        Args:
            message: Message to broadcast
            exclude_username: Username to exclude from broadcast (e.g., the sender)
        """
        disconnected_users = []

        # Fetch sender user info for display
        from .storage import storage

        from_user = storage.get_user_by_username(message.from_username)
        message_data = MessageResponse.from_message(message, from_user=from_user).model_dump()

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


async def websocket_auth(websocket: WebSocket) -> User | None:
    """Authenticate a WebSocket connection.

    Supports dual authentication:
    - API key via query parameter: ?api_key=KEY
    - API key via X-API-Key header
    - Stytch session token via Authorization: Bearer <token> header

    Args:
        websocket: WebSocket connection

    Returns:
        Authenticated user or None if authentication fails
    """
    # Try API key authentication first (query param or header)
    api_key = websocket.query_params.get("api_key")

    if not api_key:
        # Try to get from headers
        api_key = websocket.headers.get("x-api-key")

    if api_key:
        user = validate_api_key(api_key)
        if user:
            return user

    # Try Stytch session token authentication
    authorization = websocket.headers.get("authorization")
    if authorization and authorization.startswith("Bearer "):
        from .stytch_client import stytch_client

        session_token = authorization[7:]  # Remove "Bearer " prefix
        stytch_user_id = await stytch_client.validate_session(session_token)

        if stytch_user_id:
            from .storage import storage

            user = storage.get_user_by_stytch_id(stytch_user_id)
            if user:
                return user

    # No valid authentication provided
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.warning(
        f"WebSocket AUTH FAILED - client: {client_host} - Invalid or missing credentials"
    )
    await websocket.close(code=1008, reason="Invalid or missing authentication credentials")
    return None
