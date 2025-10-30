"""WebSocket heartbeat mechanism to keep connections alive and detect stale connections."""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Configuration constants
HEARTBEAT_INTERVAL = 30  # Send ping every 30 seconds
PONG_TIMEOUT = 10  # Wait up to 10 seconds for pong response
CONNECTION_TIMEOUT = 90  # Consider connection dead if no activity for 90 seconds


class WebSocketHeartbeat:
    """Manages heartbeat/ping-pong for WebSocket connections."""

    def __init__(self) -> None:
        """Initialize the heartbeat manager."""
        self.active_connections: dict[str, dict] = {}  # username -> connection info
        self.heartbeat_tasks: dict[str, asyncio.Task] = {}  # username -> heartbeat task

    def track_connection(self, username: str, websocket: WebSocket) -> None:
        """Start tracking a WebSocket connection.

        Args:
            username: Username of the connected user
            websocket: WebSocket connection
        """
        self.active_connections[username] = {
            "websocket": websocket,
            "last_activity": datetime.now(UTC),
            "last_pong": datetime.now(UTC),
        }
        logger.debug(f"Started tracking connection for {username}")

    def untrack_connection(self, username: str) -> None:
        """Stop tracking a WebSocket connection.

        Args:
            username: Username to stop tracking
        """
        if username in self.active_connections:
            del self.active_connections[username]
            logger.debug(f"Stopped tracking connection for {username}")

        # Cancel heartbeat task if running
        if username in self.heartbeat_tasks:
            task = self.heartbeat_tasks[username]
            if not task.done():
                task.cancel()
            del self.heartbeat_tasks[username]
            logger.debug(f"Cancelled heartbeat task for {username}")

    def update_activity(self, username: str) -> None:
        """Update last activity timestamp for a connection.

        Args:
            username: Username whose activity to update
        """
        if username in self.active_connections:
            self.active_connections[username]["last_activity"] = datetime.now(UTC)

    def update_pong_received(self, username: str) -> None:
        """Update timestamp when pong was received.

        Args:
            username: Username who sent the pong
        """
        if username in self.active_connections:
            self.active_connections[username]["last_pong"] = datetime.now(UTC)
            self.active_connections[username]["last_activity"] = datetime.now(UTC)
            logger.debug(f"Received pong from {username}")

    async def send_ping(self, username: str) -> bool:
        """Send a ping message to a specific connection.

        Args:
            username: Username to ping

        Returns:
            True if ping was sent successfully, False otherwise
        """
        conn_info = self.active_connections.get(username)
        if not conn_info:
            return False

        websocket = conn_info["websocket"]
        try:
            # Send a JSON ping message that the client can respond to
            # This ensures compatibility with various WebSocket clients
            await websocket.send_json({"type": "ping", "timestamp": datetime.now(UTC).isoformat()})
            logger.debug(f"Sent ping to {username}")
            return True
        except Exception as e:
            logger.error(f"Failed to send ping to {username}: {e}")
            return False

    async def heartbeat_loop(self, username: str) -> None:
        """Run heartbeat loop for a specific connection.

        Args:
            username: Username to monitor
        """
        logger.info(f"Starting heartbeat loop for {username}")

        while username in self.active_connections:
            try:
                # Wait for heartbeat interval
                await asyncio.sleep(HEARTBEAT_INTERVAL)

                if username not in self.active_connections:
                    break

                conn_info = self.active_connections[username]
                now = datetime.now(UTC)

                # Check if connection is stale
                last_activity = conn_info["last_activity"]
                time_since_activity = (now - last_activity).total_seconds()

                if time_since_activity > CONNECTION_TIMEOUT:
                    logger.warning(
                        f"Connection for {username} is stale "
                        f"(no activity for {time_since_activity:.1f} seconds)"
                    )
                    # Return False to signal disconnection
                    from .websocket import connection_manager

                    connection_manager.disconnect(username)
                    break

                # Send ping
                if not await self.send_ping(username):
                    logger.warning(f"Failed to send ping to {username}, disconnecting")
                    from .websocket import connection_manager

                    connection_manager.disconnect(username)
                    break

            except asyncio.CancelledError:
                logger.debug(f"Heartbeat loop cancelled for {username}")
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop for {username}: {e}")
                await asyncio.sleep(HEARTBEAT_INTERVAL)  # Continue after error

        logger.info(f"Heartbeat loop ended for {username}")

    def start_heartbeat(self, username: str) -> None:
        """Start heartbeat monitoring for a connection.

        Args:
            username: Username to monitor
        """
        if username in self.heartbeat_tasks:
            # Cancel existing task if any
            task = self.heartbeat_tasks[username]
            if not task.done():
                task.cancel()

        # Start new heartbeat task
        task = asyncio.create_task(self.heartbeat_loop(username))
        self.heartbeat_tasks[username] = task
        logger.info(f"Started heartbeat monitoring for {username}")

    def is_connection_healthy(self, username: str) -> bool:
        """Check if a connection is healthy based on activity.

        Args:
            username: Username to check

        Returns:
            True if connection is healthy, False otherwise
        """
        conn_info = self.active_connections.get(username)
        if not conn_info:
            return False

        now = datetime.now(UTC)
        last_activity = conn_info["last_activity"]
        time_since_activity = (now - last_activity).total_seconds()

        return bool(time_since_activity < CONNECTION_TIMEOUT)

    def get_connection_stats(self, username: str) -> dict | None:
        """Get connection statistics for debugging.

        Args:
            username: Username to get stats for

        Returns:
            Dictionary with connection stats or None if not connected
        """
        conn_info = self.active_connections.get(username)
        if not conn_info:
            return None

        now = datetime.now(UTC)
        return {
            "username": username,
            "last_activity": conn_info["last_activity"].isoformat(),
            "last_pong": conn_info["last_pong"].isoformat(),
            "seconds_since_activity": (now - conn_info["last_activity"]).total_seconds(),
            "seconds_since_pong": (now - conn_info["last_pong"]).total_seconds(),
            "is_healthy": self.is_connection_healthy(username),
        }


# Global heartbeat manager instance
heartbeat_manager = WebSocketHeartbeat()
