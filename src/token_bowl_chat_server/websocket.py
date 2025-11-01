"""WebSocket connection management for real-time messaging."""

import asyncio
import logging

from fastapi import WebSocket

from .auth import validate_api_key
from .models import Message, MessageResponse, User
from .websocket_heartbeat import heartbeat_manager

logger = logging.getLogger(__name__)

# Timeout for WebSocket send operations (in seconds)
# If a send takes longer than this, the connection is likely broken
WEBSOCKET_SEND_TIMEOUT = 5.0


class ConnectionManager:
    """Manages WebSocket connections for users."""

    def __init__(self) -> None:
        """Initialize connection manager."""
        self.active_connections: dict[str, list[WebSocket]] = {}  # username -> list of WebSockets

    async def connect(self, websocket: WebSocket, user: User) -> None:
        """Accept a WebSocket connection for a user.

        Args:
            websocket: WebSocket connection
            user: Authenticated user
        """
        await websocket.accept()

        # Add connection to the list for this user
        if user.username not in self.active_connections:
            self.active_connections[user.username] = []
        self.active_connections[user.username].append(websocket)

        # Start heartbeat monitoring for this specific connection
        heartbeat_manager.track_connection(user.username, websocket)
        heartbeat_manager.start_heartbeat(user.username, websocket)

        client_host = websocket.client.host if websocket.client else "unknown"
        connection_count = len(self.active_connections[user.username])
        logger.info(
            f"WebSocket CONNECTED - user: {user.username}, client: {client_host}, connections: {connection_count}"
        )

    def disconnect(self, username: str, websocket: WebSocket) -> None:
        """Remove a specific WebSocket connection for a user.

        Args:
            username: Username of the connection
            websocket: Specific WebSocket connection to remove
        """
        if username in self.active_connections:
            connections = self.active_connections[username]
            if websocket in connections:
                connections.remove(websocket)

                # If no more connections for this user, remove the entry
                if not connections:
                    del self.active_connections[username]

                # Stop heartbeat monitoring for this specific connection
                heartbeat_manager.untrack_connection(username, websocket)

                remaining = len(self.active_connections.get(username, []))
                logger.info(
                    f"WebSocket DISCONNECTED - user: {username}, remaining connections: {remaining}"
                )

    async def send_message(self, username: str, message: Message) -> bool:
        """Send a message to all active connections for a user.

        Args:
            username: Username to send message to
            message: Message to send

        Returns:
            True if message was sent to at least one connection, False otherwise
        """
        websockets = self.active_connections.get(username, [])
        if not websockets:
            logger.info(
                f"Cannot send direct message to {username} from {message.from_username}: no active connections"
            )
            return False

        # Fetch sender and recipient user info for display
        from .storage import storage

        from_user = storage.get_user_by_username(message.from_username)
        to_user = storage.get_user_by_username(message.to_username) if message.to_username else None
        message_data = MessageResponse.from_message(
            message, from_user=from_user, to_user=to_user
        ).model_dump()

        logger.info(
            f"Sending direct message from {message.from_username} to {username} "
            f"({len(websockets)} connections)"
        )

        sent_count = 0
        disconnected = []

        # Send to all connections for this user
        for idx, websocket in enumerate(websockets[:]):  # Create copy to iterate safely
            try:
                # Add timeout to prevent hanging on broken connections
                await asyncio.wait_for(
                    websocket.send_json(message_data), timeout=WEBSOCKET_SEND_TIMEOUT
                )
                sent_count += 1
                logger.info(
                    f"✓ Sent direct message to {username} (connection {idx + 1}/{len(websockets)})"
                )
            except TimeoutError:
                logger.error(
                    f"✗ Timeout sending message to {username} (connection {idx + 1}/{len(websockets)}) - connection likely broken"
                )
                disconnected.append(websocket)
            except Exception as e:
                logger.error(
                    f"✗ Error sending message to {username} (connection {idx + 1}/{len(websockets)}): {e}"
                )
                disconnected.append(websocket)

        logger.info(f"Direct message send complete: {sent_count} sent, {len(disconnected)} failed")

        # Clean up disconnected connections
        for websocket in disconnected:
            self.disconnect(username, websocket)

        return sent_count > 0

    async def send_notification(self, username: str, notification: dict) -> bool:
        """Send a notification to all active connections for a user.

        Args:
            username: Username to send notification to
            notification: Notification data to send

        Returns:
            True if notification was sent to at least one connection, False otherwise
        """
        websockets = self.active_connections.get(username, [])
        if not websockets:
            return False

        sent_count = 0
        disconnected = []

        # Send to all connections for this user
        for websocket in websockets[:]:  # Create copy to iterate safely
            try:
                # Add timeout to prevent hanging on broken connections
                await asyncio.wait_for(
                    websocket.send_json(notification), timeout=WEBSOCKET_SEND_TIMEOUT
                )
                sent_count += 1
                logger.debug(
                    f"Sent notification to {username} via WebSocket (connection {sent_count}/{len(websockets)})"
                )
            except TimeoutError:
                logger.error(
                    f"Timeout sending notification to {username} on connection (connection likely broken)"
                )
                disconnected.append(websocket)
            except Exception as e:
                logger.error(f"Error sending notification to {username} on connection: {e}")
                disconnected.append(websocket)

        # Clean up disconnected connections
        for websocket in disconnected:
            self.disconnect(username, websocket)

        return sent_count > 0

    async def broadcast_to_room(
        self, message: Message, exclude_username: str | None = None
    ) -> None:
        """Broadcast a message to all connected users.

        Args:
            message: Message to broadcast
            exclude_username: Username to exclude from broadcast (e.g., the sender)
        """
        disconnected_connections = []

        # Fetch sender user info for display
        from .storage import storage

        from_user = storage.get_user_by_username(message.from_username)
        message_data = MessageResponse.from_message(message, from_user=from_user).model_dump()

        # Log broadcast details
        total_connections = sum(len(ws_list) for ws_list in self.active_connections.values())
        logger.info(
            f"Broadcasting message from {message.from_username} to {len(self.active_connections)} users "
            f"({total_connections} total connections), excluding: {exclude_username or 'none'}"
        )

        sent_count = 0
        for username, websockets in self.active_connections.items():
            if exclude_username and username == exclude_username:
                logger.debug(f"Skipping sender {username}")
                continue

            # Send to all connections for each user
            for idx, websocket in enumerate(websockets[:]):  # Create copy to iterate safely
                try:
                    # Add timeout to prevent hanging on broken connections
                    await asyncio.wait_for(
                        websocket.send_json(message_data), timeout=WEBSOCKET_SEND_TIMEOUT
                    )
                    sent_count += 1
                    logger.info(
                        f"✓ Broadcasted message to {username} (connection {idx + 1}/{len(websockets)})"
                    )
                except TimeoutError:
                    logger.error(
                        f"✗ Timeout broadcasting to {username} (connection {idx + 1}/{len(websockets)}) - connection likely broken"
                    )
                    disconnected_connections.append((username, websocket))
                except Exception as e:
                    logger.error(
                        f"✗ Error broadcasting to {username} (connection {idx + 1}/{len(websockets)}): {e}"
                    )
                    disconnected_connections.append((username, websocket))

        logger.info(
            f"Broadcast complete: {sent_count} messages sent, {len(disconnected_connections)} failed"
        )

        # Clean up disconnected connections
        for username, websocket in disconnected_connections:
            self.disconnect(username, websocket)

    def get_connected_users(self) -> list[str]:
        """Get list of currently connected usernames.

        Returns:
            List of connected usernames
        """
        return list(self.active_connections.keys())

    def is_connected(self, username: str) -> bool:
        """Check if a user has any active connections.

        Args:
            username: Username to check

        Returns:
            True if user has at least one connection, False otherwise
        """
        return username in self.active_connections and len(self.active_connections[username]) > 0

    def is_connection_healthy(self, username: str) -> bool:
        """Check if a user has any healthy connections.

        Args:
            username: Username to check

        Returns:
            True if user has at least one healthy connection, False otherwise
        """
        if username not in self.active_connections:
            return False

        # Check if any connection is healthy
        for websocket in self.active_connections[username]:
            if heartbeat_manager.is_connection_healthy(username, websocket):
                return True
        return False


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
