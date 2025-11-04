"""Tests for Centrifugo integration."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import jwt
import pytest

from token_bowl_chat_server.centrifugo_client import CentrifugoClient


def test_get_centrifugo_connection_token(client, registered_user):
    """Test getting a Centrifugo connection token."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/centrifugo/connection-token", headers=headers)

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "token" in data
    assert "url" in data
    assert "user" in data
    assert data["user"] == "test_user"
    assert "ws://localhost:8001/connection/websocket" in data["url"]

    # Verify JWT token
    token = data["token"]
    decoded = jwt.decode(token, "your-secret-key-change-in-production", algorithms=["HS256"])
    assert decoded["sub"] == "test_user"
    assert "exp" in decoded
    assert "iat" in decoded


def test_get_centrifugo_connection_token_requires_auth(client):
    """Test that connection token endpoint requires authentication."""
    response = client.get("/centrifugo/connection-token")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_centrifugo_client_generate_token():
    """Test Centrifugo client token generation."""
    from token_bowl_chat_server.models import User

    client = CentrifugoClient(
        api_url="http://localhost:8001/api", api_key="test-key", token_secret="test-secret"
    )

    # Create a user with a proper 64-char API key
    user = User(
        id="550e8400-e29b-41d4-a716-446655440000",
        username="testuser",
        api_key="a" * 64,  # Valid 64-char API key
        created_at=datetime.now(UTC),
    )

    token = client.generate_connection_token(user)

    # Verify it's a valid JWT
    decoded = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert decoded["sub"] == "testuser"
    assert "exp" in decoded
    assert "iat" in decoded


def test_send_room_message_publishes_to_centrifugo(client, registered_user):
    """Test that sending a room message publishes to Centrifugo."""
    from token_bowl_chat_server.centrifugo_client import get_centrifugo_client

    # Get the actual Centrifugo client and mock its publish method
    centrifugo = get_centrifugo_client()

    with patch.object(centrifugo, "publish_room_message", new_callable=AsyncMock) as mock_publish:
        headers = {"X-API-Key": registered_user["api_key"]}
        response = client.post(
            "/messages",
            json={"content": "Hello, room!"},
            headers=headers,
        )

        assert response.status_code == 201

        # Verify Centrifugo publish was called
        mock_publish.assert_called_once()

        # Verify the message and user were passed
        call_args = mock_publish.call_args[0]
        message = call_args[0]  # First positional argument
        from_user = call_args[1]  # Second positional argument

        assert message.content == "Hello, room!"
        assert message.message_type == "room"
        assert from_user.username == "test_user"


def test_send_direct_message_publishes_to_centrifugo(client, registered_user, registered_user2):
    """Test that sending a direct message publishes to Centrifugo."""
    from token_bowl_chat_server.centrifugo_client import get_centrifugo_client

    # Get the actual Centrifugo client and mock its publish method
    centrifugo = get_centrifugo_client()

    with patch.object(centrifugo, "publish_direct_message", new_callable=AsyncMock) as mock_publish:
        headers = {"X-API-Key": registered_user["api_key"]}
        response = client.post(
            "/messages",
            json={"content": "Private message", "to_username": "test_user2"},
            headers=headers,
        )

        assert response.status_code == 201

        # Verify Centrifugo publish was called
        mock_publish.assert_called_once()

        # Verify the message and users were passed
        call_args = mock_publish.call_args[0]
        message = call_args[0]  # First positional argument
        from_user = call_args[1]  # Second positional argument
        to_user = call_args[2]  # Third positional argument

        assert message.content == "Private message"
        assert message.message_type == "direct"
        assert from_user.username == "test_user"
        assert to_user.username == "test_user2"


def test_centrifugo_success_with_mock(client, registered_user):
    """Test that messages publish successfully when Centrifugo is available."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.post(
        "/messages",
        json={"content": "Hello, room!"},
        headers=headers,
    )

    # With the mocked Centrifugo client, requests should succeed
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == "Hello, room!"


@pytest.mark.asyncio
async def test_centrifugo_disconnect_user_method():
    """Test that disconnect_user method exists and is callable."""
    from token_bowl_chat_server.centrifugo_client import get_centrifugo_client

    centrifugo = get_centrifugo_client()

    # Verify the disconnect_user method is an AsyncMock
    assert hasattr(centrifugo, "disconnect_user")
    assert centrifugo.disconnect_user is not None

    # Call it and verify it doesn't raise
    await centrifugo.disconnect_user("testuser")


def test_centrifugo_token_includes_user_info(client, registered_user):
    """Test that Centrifugo tokens contain correct user information."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/centrifugo/connection-token", headers=headers)

    assert response.status_code == 200
    data = response.json()
    token = data["token"]

    # Decode and verify claims
    decoded = jwt.decode(token, "your-secret-key-change-in-production", algorithms=["HS256"])

    # Verify user identifier
    assert decoded["sub"] == "test_user"

    # Verify token expiration is in the future
    assert decoded["exp"] > decoded["iat"]

    # Verify token is valid for reasonable duration (should be ~24 hours)
    duration_seconds = decoded["exp"] - decoded["iat"]
    assert 23 * 3600 < duration_seconds < 25 * 3600  # Between 23-25 hours


def test_multiple_users_get_different_tokens(client, registered_user, registered_user2):
    """Test that different users get different connection tokens."""
    headers1 = {"X-API-Key": registered_user["api_key"]}
    response1 = client.get("/centrifugo/connection-token", headers=headers1)

    headers2 = {"X-API-Key": registered_user2["api_key"]}
    response2 = client.get("/centrifugo/connection-token", headers=headers2)

    assert response1.status_code == 200
    assert response2.status_code == 200

    token1 = response1.json()["token"]
    token2 = response2.json()["token"]

    # Tokens should be different
    assert token1 != token2

    # Decode and verify they're for different users
    decoded1 = jwt.decode(token1, "your-secret-key-change-in-production", algorithms=["HS256"])
    decoded2 = jwt.decode(token2, "your-secret-key-change-in-production", algorithms=["HS256"])

    assert decoded1["sub"] == "test_user"
    assert decoded2["sub"] == "test_user2"
