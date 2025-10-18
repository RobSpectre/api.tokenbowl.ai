"""Tests for WebSocket connection management."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from token_bowl_chat_server.models import Message, MessageType, User
from token_bowl_chat_server.websocket import ConnectionManager, websocket_auth


@pytest.fixture
def manager():
    """Create a fresh ConnectionManager for each test."""
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect(manager):
    """Test connecting a user."""
    websocket = AsyncMock()
    user = User(username="test_user", api_key="a" * 64)

    await manager.connect(websocket, user)

    websocket.accept.assert_called_once()
    assert "test_user" in manager.active_connections
    assert manager.active_connections["test_user"] == websocket


@pytest.mark.asyncio
async def test_disconnect(manager):
    """Test disconnecting a user."""
    websocket = AsyncMock()
    user = User(username="test_user", api_key="a" * 64)

    # Connect first
    await manager.connect(websocket, user)
    assert "test_user" in manager.active_connections

    # Disconnect
    manager.disconnect("test_user")
    assert "test_user" not in manager.active_connections


def test_disconnect_nonexistent_user(manager):
    """Test disconnecting a user that's not connected."""
    # Should not raise an error
    manager.disconnect("nonexistent_user")
    assert "nonexistent_user" not in manager.active_connections


@pytest.mark.asyncio
async def test_send_message_success(manager):
    """Test sending a message successfully."""
    websocket = AsyncMock()
    user = User(username="test_user", api_key="a" * 64)
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    # Connect user
    await manager.connect(websocket, user)

    # Send message
    result = await manager.send_message("test_user", message)

    assert result is True
    websocket.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_send_message_user_not_connected(manager):
    """Test sending a message to disconnected user."""
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    result = await manager.send_message("nonexistent_user", message)
    assert result is False


@pytest.mark.asyncio
async def test_send_message_error(manager):
    """Test sending a message with error."""
    websocket = AsyncMock()
    websocket.send_json.side_effect = Exception("Send error")
    user = User(username="test_user", api_key="a" * 64)
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    # Connect user
    await manager.connect(websocket, user)

    # Send message (should fail and disconnect)
    result = await manager.send_message("test_user", message)

    assert result is False
    # User should be disconnected after error
    assert "test_user" not in manager.active_connections


@pytest.mark.asyncio
async def test_broadcast_to_room(manager):
    """Test broadcasting to all connected users."""
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()
    user1 = User(username="user1", api_key="a" * 64)
    user2 = User(username="user2", api_key="b" * 64)
    message = Message(
        from_username="sender",
        content="Broadcast message",
        message_type=MessageType.ROOM,
    )

    # Connect users
    await manager.connect(websocket1, user1)
    await manager.connect(websocket2, user2)

    # Broadcast
    await manager.broadcast_to_room(message)

    # Both should receive the message
    websocket1.send_json.assert_called_once()
    websocket2.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_broadcast_to_room_with_exclusion(manager):
    """Test broadcasting with sender exclusion."""
    websocket1 = AsyncMock()
    websocket2 = AsyncMock()
    user1 = User(username="user1", api_key="a" * 64)
    user2 = User(username="user2", api_key="b" * 64)
    message = Message(
        from_username="user1",
        content="Broadcast message",
        message_type=MessageType.ROOM,
    )

    # Connect users
    await manager.connect(websocket1, user1)
    await manager.connect(websocket2, user2)

    # Broadcast excluding user1
    await manager.broadcast_to_room(message, exclude_username="user1")

    # Only user2 should receive
    websocket1.send_json.assert_not_called()
    websocket2.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_broadcast_to_room_with_error(manager):
    """Test broadcasting with error on one connection."""
    websocket1 = AsyncMock()
    websocket1.send_json.side_effect = Exception("Send error")
    websocket2 = AsyncMock()
    user1 = User(username="user1", api_key="a" * 64)
    user2 = User(username="user2", api_key="b" * 64)
    message = Message(
        from_username="sender",
        content="Broadcast message",
        message_type=MessageType.ROOM,
    )

    # Connect users
    await manager.connect(websocket1, user1)
    await manager.connect(websocket2, user2)

    # Broadcast
    await manager.broadcast_to_room(message)

    # user1 should be disconnected, user2 should receive
    assert "user1" not in manager.active_connections
    assert "user2" in manager.active_connections
    websocket2.send_json.assert_called_once()


def test_get_connected_users(manager):
    """Test getting list of connected users."""
    assert manager.get_connected_users() == []

    # Add some users manually
    manager.active_connections["user1"] = MagicMock()
    manager.active_connections["user2"] = MagicMock()

    connected = manager.get_connected_users()
    assert len(connected) == 2
    assert "user1" in connected
    assert "user2" in connected


def test_is_connected(manager):
    """Test checking if user is connected."""
    assert manager.is_connected("user1") is False

    manager.active_connections["user1"] = MagicMock()

    assert manager.is_connected("user1") is True
    assert manager.is_connected("user2") is False


@pytest.mark.asyncio
async def test_websocket_auth_query_param(test_storage):
    """Test WebSocket authentication with query parameter."""
    # Create a user
    user = User(username="test_user", api_key="a" * 64)
    test_storage.add_user(user)

    # Mock WebSocket with API key in query params
    websocket = AsyncMock()
    websocket.query_params = {"api_key": "a" * 64}
    websocket.headers = {}

    result = await websocket_auth(websocket)

    assert result is not None
    assert result.username == "test_user"
    websocket.close.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_auth_header(test_storage):
    """Test WebSocket authentication with header."""
    # Create a user
    user = User(username="test_user", api_key="a" * 64)
    test_storage.add_user(user)

    # Mock WebSocket with API key in header
    websocket = AsyncMock()
    websocket.query_params = {}
    websocket.headers = {"x-api-key": "a" * 64}

    result = await websocket_auth(websocket)

    assert result is not None
    assert result.username == "test_user"
    websocket.close.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_auth_missing_key():
    """Test WebSocket authentication with missing credentials."""
    websocket = AsyncMock()
    websocket.query_params = {}
    websocket.headers = {}

    result = await websocket_auth(websocket)

    assert result is None
    websocket.close.assert_called_once_with(
        code=1008, reason="Invalid or missing authentication credentials"
    )


@pytest.mark.asyncio
async def test_websocket_auth_invalid_key():
    """Test WebSocket authentication with invalid API key."""
    websocket = AsyncMock()
    websocket.query_params = {"api_key": "invalid_key"}
    websocket.headers = {}

    result = await websocket_auth(websocket)

    assert result is None
    websocket.close.assert_called_once_with(
        code=1008, reason="Invalid or missing authentication credentials"
    )


@pytest.mark.asyncio
async def test_websocket_auth_stytch_session_token(test_storage):
    """Test WebSocket authentication with Stytch session token."""
    # Create a user with Stytch ID
    user = User(username="test_user", api_key="a" * 64, stytch_user_id="stytch_123")
    test_storage.add_user(user)

    # Mock WebSocket with Stytch session token in Authorization header
    websocket = AsyncMock()
    websocket.query_params = {}
    websocket.headers = {"authorization": "Bearer valid_session_token"}

    # Mock stytch_client.validate_session to return the Stytch user ID
    with patch("token_bowl_chat_server.stytch_client.stytch_client") as mock_stytch:
        mock_stytch.validate_session = AsyncMock(return_value="stytch_123")

        result = await websocket_auth(websocket)

        assert result is not None
        assert result.username == "test_user"
        assert result.stytch_user_id == "stytch_123"
        websocket.close.assert_not_called()
        mock_stytch.validate_session.assert_called_once_with("valid_session_token")


@pytest.mark.asyncio
async def test_websocket_auth_invalid_stytch_token():
    """Test WebSocket authentication with invalid Stytch session token."""
    websocket = AsyncMock()
    websocket.query_params = {}
    websocket.headers = {"authorization": "Bearer invalid_session_token"}

    # Mock stytch_client.validate_session to return None (invalid token)
    with patch("token_bowl_chat_server.stytch_client.stytch_client") as mock_stytch:
        mock_stytch.validate_session = AsyncMock(return_value=None)

        result = await websocket_auth(websocket)

        assert result is None
        websocket.close.assert_called_once_with(
            code=1008, reason="Invalid or missing authentication credentials"
        )
        mock_stytch.validate_session.assert_called_once_with("invalid_session_token")


@pytest.mark.asyncio
async def test_websocket_auth_stytch_token_user_not_found(test_storage):
    """Test WebSocket authentication when Stytch user doesn't exist in database."""
    websocket = AsyncMock()
    websocket.query_params = {}
    websocket.headers = {"authorization": "Bearer valid_session_token"}

    # Mock stytch_client.validate_session to return a Stytch ID that's not in the database
    with patch("token_bowl_chat_server.stytch_client.stytch_client") as mock_stytch:
        mock_stytch.validate_session = AsyncMock(return_value="nonexistent_stytch_id")

        result = await websocket_auth(websocket)

        assert result is None
        websocket.close.assert_called_once_with(
            code=1008, reason="Invalid or missing authentication credentials"
        )


@pytest.mark.asyncio
async def test_websocket_auth_api_key_priority(test_storage):
    """Test that API key authentication is tried before Stytch token."""
    # Create a user
    user = User(username="test_user", api_key="a" * 64)
    test_storage.add_user(user)

    # Mock WebSocket with both API key and Stytch token
    websocket = AsyncMock()
    websocket.query_params = {"api_key": "a" * 64}
    websocket.headers = {"authorization": "Bearer some_session_token"}

    # Mock stytch_client - should not be called since API key is valid
    with patch("token_bowl_chat_server.stytch_client.stytch_client") as mock_stytch:
        mock_stytch.validate_session = AsyncMock(return_value="stytch_123")

        result = await websocket_auth(websocket)

        assert result is not None
        assert result.username == "test_user"
        # Stytch validation should not have been called
        mock_stytch.validate_session.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_auth_malformed_authorization_header():
    """Test WebSocket authentication with malformed Authorization header."""
    websocket = AsyncMock()
    websocket.query_params = {}
    websocket.headers = {"authorization": "InvalidFormat"}  # Missing "Bearer " prefix

    result = await websocket_auth(websocket)

    assert result is None
    websocket.close.assert_called_once_with(
        code=1008, reason="Invalid or missing authentication credentials"
    )
