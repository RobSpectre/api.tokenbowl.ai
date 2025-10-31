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
        # Use WebSocket object as key for connection-specific tracking
        self.active_connections: dict[
            tuple[str, WebSocket], dict
        ] = {}  # (username, websocket) -> connection info
        self.heartbeat_tasks: dict[
            tuple[str, WebSocket], asyncio.Task
        ] = {}  # (username, websocket) -> heartbeat task

    def track_connection(self, username: str, websocket: WebSocket) -> None:
        """Start tracking a WebSocket connection.

        Args:
            username: Username of the connected user
            websocket: WebSocket connection
        """
        key = (username, websocket)
        self.active_connections[key] = {
            "websocket": websocket,
            "username": username,
            "last_activity": datetime.now(UTC),
            "last_pong": datetime.now(UTC),
        }
        logger.debug(f"Started tracking connection for {username}")

    def untrack_connection(self, username: str, websocket: WebSocket) -> None:
        """Stop tracking a WebSocket connection.

        Args:
            username: Username to stop tracking
            websocket: Specific WebSocket connection to untrack
        """
        key = (username, websocket)
        if key in self.active_connections:
            del self.active_connections[key]
            logger.debug(f"Stopped tracking connection for {username}")

        # Cancel heartbeat task if running
        if key in self.heartbeat_tasks:
            task = self.heartbeat_tasks[key]
            if not task.done():
                task.cancel()
            del self.heartbeat_tasks[key]
            logger.debug(f"Cancelled heartbeat task for {username}")

    def update_activity(self, username: str, websocket: WebSocket) -> None:
        """Update last activity timestamp for a specific connection.

        Args:
            username: Username whose activity to update
            websocket: Specific WebSocket connection
        """
        key = (username, websocket)
        if key in self.active_connections:
            self.active_connections[key]["last_activity"] = datetime.now(UTC)

    def update_pong_received(self, username: str, websocket: WebSocket) -> None:
        """Update timestamp when pong was received for a specific connection.

        Args:
            username: Username who sent the pong
            websocket: Specific WebSocket connection
        """
        key = (username, websocket)
        if key in self.active_connections:
            self.active_connections[key]["last_pong"] = datetime.now(UTC)
            self.active_connections[key]["last_activity"] = datetime.now(UTC)
            logger.debug(f"Received pong from {username}")

    async def send_ping(self, username: str, websocket: WebSocket) -> bool:
        """Send a ping message to a specific connection.

        Args:
            username: Username to ping
            websocket: Specific WebSocket connection

        Returns:
            True if ping was sent successfully, False otherwise
        """
        key = (username, websocket)
        conn_info = self.active_connections.get(key)
        if not conn_info:
            return False

        try:
            # Send a JSON ping message that the client can respond to
            # This ensures compatibility with various WebSocket clients
            await websocket.send_json({"type": "ping", "timestamp": datetime.now(UTC).isoformat()})
            logger.debug(f"Sent ping to {username}")
            return True
        except Exception as e:
            logger.error(f"Failed to send ping to {username}: {e}")
            return False

    async def heartbeat_loop(self, username: str, websocket: WebSocket) -> None:
        """Run heartbeat loop for a specific connection.

        Args:
            username: Username to monitor
            websocket: Specific WebSocket connection
        """
        logger.info(f"Starting heartbeat loop for {username}")
        key = (username, websocket)

        while key in self.active_connections:
            try:
                # Wait for heartbeat interval
                await asyncio.sleep(HEARTBEAT_INTERVAL)

                if key not in self.active_connections:
                    break

                conn_info = self.active_connections[key]
                now = datetime.now(UTC)

                # Check if connection is stale
                last_activity = conn_info["last_activity"]
                time_since_activity = (now - last_activity).total_seconds()

                if time_since_activity > CONNECTION_TIMEOUT:
                    logger.warning(
                        f"Connection for {username} is stale "
                        f"(no activity for {time_since_activity:.1f} seconds)"
                    )
                    # Disconnect this specific connection
                    from .websocket import connection_manager

                    connection_manager.disconnect(username, websocket)
                    break

                # Send ping
                if not await self.send_ping(username, websocket):
                    logger.warning(f"Failed to send ping to {username}, disconnecting")
                    from .websocket import connection_manager

                    connection_manager.disconnect(username, websocket)
                    break

            except asyncio.CancelledError:
                logger.debug(f"Heartbeat loop cancelled for {username}")
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop for {username}: {e}")
                await asyncio.sleep(HEARTBEAT_INTERVAL)  # Continue after error

        logger.info(f"Heartbeat loop ended for {username}")

    def start_heartbeat(self, username: str, websocket: WebSocket | None = None) -> None:
        """Start heartbeat monitoring for a specific connection.

        Args:
            username: Username to monitor
            websocket: Specific WebSocket connection (for backward compatibility, can be None)
        """
        # For backward compatibility - if no websocket provided, start for all connections
        if websocket is None:
            # Start heartbeat for all connections of this user
            for user, ws in self.active_connections.keys():
                if user == username:
                    self.start_heartbeat(user, ws)
            return

        key = (username, websocket)
        if key in self.heartbeat_tasks:
            # Cancel existing task if any
            task = self.heartbeat_tasks[key]
            if not task.done():
                task.cancel()

        # Start new heartbeat task
        task = asyncio.create_task(self.heartbeat_loop(username, websocket))
        self.heartbeat_tasks[key] = task
        logger.info(f"Started heartbeat monitoring for {username}")

    def is_connection_healthy(self, username: str, websocket: WebSocket) -> bool:
        """Check if a specific connection is healthy based on activity.

        Args:
            username: Username to check
            websocket: Specific WebSocket connection

        Returns:
            True if connection is healthy, False otherwise
        """
        key = (username, websocket)
        conn_info = self.active_connections.get(key)
        if not conn_info:
            return False

        now = datetime.now(UTC)
        last_activity = conn_info["last_activity"]
        time_since_activity = (now - last_activity).total_seconds()

        return bool(time_since_activity < CONNECTION_TIMEOUT)

    def get_connection_stats(self, username: str) -> list[dict] | None:
        """Get connection statistics for all connections of a user.

        Args:
            username: Username to get stats for

        Returns:
            List of dictionaries with connection stats or None if not connected
        """
        stats = []
        now = datetime.now(UTC)

        for user, websocket in self.active_connections.keys():
            if user == username:
                key = (user, websocket)
                conn_info = self.active_connections[key]
                stats.append(
                    {
                        "username": username,
                        "connection_id": id(websocket),  # Use object id as connection identifier
                        "last_activity": conn_info["last_activity"].isoformat(),
                        "last_pong": conn_info["last_pong"].isoformat(),
                        "seconds_since_activity": (
                            now - conn_info["last_activity"]
                        ).total_seconds(),
                        "seconds_since_pong": (now - conn_info["last_pong"]).total_seconds(),
                        "is_healthy": self.is_connection_healthy(username, websocket),
                    }
                )

        return stats if stats else None


# Global heartbeat manager instance
heartbeat_manager = WebSocketHeartbeat()
