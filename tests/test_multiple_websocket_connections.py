"""Tests for multiple concurrent WebSocket connections from the same user."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket

from token_bowl_chat_server.models import Message, MessageType, User
from token_bowl_chat_server.websocket import ConnectionManager
from token_bowl_chat_server.websocket_heartbeat import WebSocketHeartbeat


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.client = MagicMock()
    ws.client.host = "test_host"
    return ws


@pytest.fixture
def mock_websocket2():
    """Create a second mock WebSocket connection."""
    ws = MagicMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.client = MagicMock()
    ws.client.host = "test_host_2"
    return ws


@pytest.fixture
def test_user():
    """Create a test user."""
    return User(
        username="test_user",
        api_key="a" * 64,  # Valid 64-character API key
        email="test@example.com",
    )


@pytest.fixture
def connection_manager():
    """Create a fresh ConnectionManager instance."""
    return ConnectionManager()


@pytest.fixture
def heartbeat_manager():
    """Create a fresh WebSocketHeartbeat instance."""
    return WebSocketHeartbeat()


@pytest.mark.asyncio
async def test_multiple_connections_same_user(
    connection_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that a user can have multiple concurrent WebSocket connections."""
    # Connect first WebSocket
    with patch("token_bowl_chat_server.websocket.heartbeat_manager") as mock_heartbeat:
        await connection_manager.connect(mock_websocket, test_user)

        # Verify first connection is stored
        assert connection_manager.is_connected(test_user.username)
        assert len(connection_manager.active_connections[test_user.username]) == 1
        assert mock_websocket in connection_manager.active_connections[test_user.username]

        # Connect second WebSocket for same user
        await connection_manager.connect(mock_websocket2, test_user)

        # Verify both connections are stored
        assert connection_manager.is_connected(test_user.username)
        assert len(connection_manager.active_connections[test_user.username]) == 2
        assert mock_websocket in connection_manager.active_connections[test_user.username]
        assert mock_websocket2 in connection_manager.active_connections[test_user.username]

        # Verify heartbeat tracking was called for both
        assert mock_heartbeat.track_connection.call_count == 2
        assert mock_heartbeat.start_heartbeat.call_count == 2


@pytest.mark.asyncio
async def test_disconnect_specific_connection(
    connection_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that disconnecting one connection doesn't affect others."""
    with patch("token_bowl_chat_server.websocket.heartbeat_manager") as mock_heartbeat:
        # Connect two WebSockets
        await connection_manager.connect(mock_websocket, test_user)
        await connection_manager.connect(mock_websocket2, test_user)

        assert len(connection_manager.active_connections[test_user.username]) == 2

        # Disconnect first WebSocket only
        connection_manager.disconnect(test_user.username, mock_websocket)

        # Verify only one connection remains
        assert connection_manager.is_connected(test_user.username)
        assert len(connection_manager.active_connections[test_user.username]) == 1
        assert mock_websocket not in connection_manager.active_connections[test_user.username]
        assert mock_websocket2 in connection_manager.active_connections[test_user.username]

        # Verify heartbeat untracking was called for the disconnected connection
        mock_heartbeat.untrack_connection.assert_called_once_with(
            test_user.username, mock_websocket
        )


@pytest.mark.asyncio
async def test_disconnect_last_connection_removes_user(
    connection_manager, test_user, mock_websocket
):
    """Test that disconnecting the last connection removes the user from active_connections."""
    with patch("token_bowl_chat_server.websocket.heartbeat_manager"):
        # Connect and then disconnect
        await connection_manager.connect(mock_websocket, test_user)
        assert test_user.username in connection_manager.active_connections

        connection_manager.disconnect(test_user.username, mock_websocket)

        # User should be completely removed from active_connections
        assert test_user.username not in connection_manager.active_connections
        assert not connection_manager.is_connected(test_user.username)


@pytest.mark.asyncio
async def test_send_message_to_multiple_connections(
    connection_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that messages are sent to all active connections for a user."""
    with patch("token_bowl_chat_server.websocket.heartbeat_manager"):
        # Connect two WebSockets
        await connection_manager.connect(mock_websocket, test_user)
        await connection_manager.connect(mock_websocket2, test_user)

        # Create a test message
        message = Message(
            from_username="sender",
            to_username=test_user.username,
            content="Test message",
            message_type=MessageType.DIRECT,
        )

        # Mock storage to return user info
        with patch("token_bowl_chat_server.storage.storage") as mock_storage:
            mock_storage.get_user_by_username.return_value = test_user

            # Send message
            result = await connection_manager.send_message(test_user.username, message)

            # Verify message was sent to both connections
            assert result is True
            assert mock_websocket.send_json.call_count == 1
            assert mock_websocket2.send_json.call_count == 1

            # Verify both received the same message data
            call_args_1 = mock_websocket.send_json.call_args[0][0]
            call_args_2 = mock_websocket2.send_json.call_args[0][0]
            assert call_args_1 == call_args_2
            assert call_args_1["content"] == "Test message"


@pytest.mark.asyncio
async def test_send_notification_to_multiple_connections(
    connection_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that notifications are sent to all active connections for a user."""
    with patch("token_bowl_chat_server.websocket.heartbeat_manager"):
        # Connect two WebSockets
        await connection_manager.connect(mock_websocket, test_user)
        await connection_manager.connect(mock_websocket2, test_user)

        # Send notification
        notification = {"type": "test_notification", "data": "test_data"}
        result = await connection_manager.send_notification(test_user.username, notification)

        # Verify notification was sent to both connections
        assert result is True
        assert mock_websocket.send_json.call_count == 1
        assert mock_websocket2.send_json.call_count == 1

        # Verify both received the same notification
        mock_websocket.send_json.assert_called_with(notification)
        mock_websocket2.send_json.assert_called_with(notification)


@pytest.mark.asyncio
async def test_broadcast_excludes_all_sender_connections(
    connection_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that broadcast excludes all connections from the sender."""
    with patch("token_bowl_chat_server.websocket.heartbeat_manager"):
        # Connect two WebSockets for the same user
        await connection_manager.connect(mock_websocket, test_user)
        await connection_manager.connect(mock_websocket2, test_user)

        # Create another user with a connection
        other_user = User(username="other_user", api_key="b" * 64, email="other@example.com")
        other_websocket = MagicMock(spec=WebSocket)
        other_websocket.accept = AsyncMock()
        other_websocket.send_json = AsyncMock()
        other_websocket.client = MagicMock()
        other_websocket.client.host = "other_host"

        await connection_manager.connect(other_websocket, other_user)

        # Create a message from test_user
        message = Message(
            from_username=test_user.username,
            to_username=None,  # Room message
            content="Broadcast message",
            message_type=MessageType.ROOM,
        )

        # Mock storage
        with patch("token_bowl_chat_server.storage.storage") as mock_storage:
            mock_storage.get_user_by_username.return_value = test_user

            # Broadcast message
            await connection_manager.broadcast_to_room(message, exclude_username=test_user.username)

            # Verify sender's connections didn't receive the message
            assert mock_websocket.send_json.call_count == 0
            assert mock_websocket2.send_json.call_count == 0

            # Verify other user's connection received the message
            assert other_websocket.send_json.call_count == 1
            call_args = other_websocket.send_json.call_args[0][0]
            assert call_args["content"] == "Broadcast message"


@pytest.mark.asyncio
async def test_failed_connection_cleanup(
    connection_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that failed connections are automatically cleaned up."""
    with patch("token_bowl_chat_server.websocket.heartbeat_manager"):
        # Connect two WebSockets
        await connection_manager.connect(mock_websocket, test_user)
        await connection_manager.connect(mock_websocket2, test_user)

        # Make first WebSocket fail on send
        mock_websocket.send_json.side_effect = Exception("Connection failed")

        # Create a test message
        message = Message(
            from_username="sender",
            to_username=test_user.username,
            content="Test message",
            message_type=MessageType.DIRECT,
        )

        # Mock storage
        with patch("token_bowl_chat_server.storage.storage") as mock_storage:
            mock_storage.get_user_by_username.return_value = test_user

            # Send message (should fail on first connection but succeed on second)
            result = await connection_manager.send_message(test_user.username, message)

            # Message should still be delivered to the working connection
            assert result is True
            assert mock_websocket2.send_json.call_count == 1

            # Failed connection should be removed
            assert len(connection_manager.active_connections[test_user.username]) == 1
            assert mock_websocket not in connection_manager.active_connections[test_user.username]
            assert mock_websocket2 in connection_manager.active_connections[test_user.username]


def test_heartbeat_tracks_individual_connections(
    heartbeat_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that heartbeat manager tracks each connection individually."""
    # Track two connections for the same user
    heartbeat_manager.track_connection(test_user.username, mock_websocket)
    heartbeat_manager.track_connection(test_user.username, mock_websocket2)

    # Both connections should be tracked
    key1 = (test_user.username, mock_websocket)
    key2 = (test_user.username, mock_websocket2)

    assert key1 in heartbeat_manager.active_connections
    assert key2 in heartbeat_manager.active_connections

    # Each connection should have its own tracking info
    assert heartbeat_manager.active_connections[key1]["websocket"] == mock_websocket
    assert heartbeat_manager.active_connections[key2]["websocket"] == mock_websocket2

    # Update activity for one connection only
    heartbeat_manager.update_activity(test_user.username, mock_websocket)

    # Only the first connection's activity should be updated
    assert heartbeat_manager.active_connections[key1]["last_activity"] is not None

    # Check if connections are healthy
    assert heartbeat_manager.is_connection_healthy(test_user.username, mock_websocket)
    assert heartbeat_manager.is_connection_healthy(test_user.username, mock_websocket2)


def test_heartbeat_untrack_specific_connection(
    heartbeat_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that heartbeat manager can untrack a specific connection."""
    # Track two connections
    heartbeat_manager.track_connection(test_user.username, mock_websocket)
    heartbeat_manager.track_connection(test_user.username, mock_websocket2)

    # Untrack first connection
    heartbeat_manager.untrack_connection(test_user.username, mock_websocket)

    # First connection should be removed, second should remain
    key1 = (test_user.username, mock_websocket)
    key2 = (test_user.username, mock_websocket2)

    assert key1 not in heartbeat_manager.active_connections
    assert key2 in heartbeat_manager.active_connections


def test_heartbeat_get_connection_stats(
    heartbeat_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that heartbeat manager returns stats for all connections of a user."""
    # Track two connections
    heartbeat_manager.track_connection(test_user.username, mock_websocket)
    heartbeat_manager.track_connection(test_user.username, mock_websocket2)

    # Get stats for the user
    stats = heartbeat_manager.get_connection_stats(test_user.username)

    # Should return stats for both connections
    assert stats is not None
    assert len(stats) == 2

    # Each stat should have connection-specific info
    connection_ids = {stat["connection_id"] for stat in stats}
    assert len(connection_ids) == 2  # Each connection has unique ID

    for stat in stats:
        assert stat["username"] == test_user.username
        assert stat["is_healthy"] is True
        assert "last_activity" in stat
        assert "last_pong" in stat
        assert "seconds_since_activity" in stat
        assert "seconds_since_pong" in stat


@pytest.mark.asyncio
async def test_connection_health_check_per_connection(
    connection_manager, test_user, mock_websocket, mock_websocket2
):
    """Test that connection health is checked per connection, not per user."""
    # Mock heartbeat manager to return different health status for each connection
    with patch("token_bowl_chat_server.websocket.heartbeat_manager") as mock_heartbeat:
        # Set up mock to return True for first connection, False for second
        def mock_is_healthy(username, websocket):
            return websocket == mock_websocket

        mock_heartbeat.is_connection_healthy.side_effect = mock_is_healthy

        # Connect two WebSockets
        await connection_manager.connect(mock_websocket, test_user)
        await connection_manager.connect(mock_websocket2, test_user)

        # Check overall connection health (should return True if any connection is healthy)
        result = connection_manager.is_connection_healthy(test_user.username)
        assert result is True

        # Verify health was checked (at least once, may return early if first is healthy)
        assert mock_heartbeat.is_connection_healthy.call_count >= 1
