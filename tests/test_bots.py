"""Tests for bot functionality."""

import pytest
from fastapi import status
from fastapi.testclient import TestClient


def test_register_bot_should_fail(client: TestClient) -> None:
    """Test that bots cannot be created via /register endpoint."""
    response = client.post(
        "/register",
        json={
            "username": "test_bot",
            "bot": True,
            "emoji": "🤖",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Bots cannot be created via /register" in response.json()["detail"]
    assert "POST /bots" in response.json()["detail"]


def test_register_bot_with_logo_should_fail(client: TestClient) -> None:
    """Test that bots cannot have logos (emoji only)."""
    response = client.post(
        "/register",
        json={
            "username": "bot_with_logo",
            "bot": True,
            "emoji": "🤖",
            "logo": "openai.png",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Bots can only use emoji for avatars" in response.json()["detail"][0]["msg"]


def test_register_bot_emoji_too_long(client: TestClient) -> None:
    """Test that emoji validation works for bots."""
    response = client.post(
        "/register",
        json={
            "username": "bad_bot",
            "bot": True,
            "emoji": "a" * 11,  # 11 chars, over the limit
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_bot_can_send_room_message(client: TestClient, registered_user: dict) -> None:
    """Test that bots can send messages to the main room."""
    # Create bot via /bots endpoint
    bot_response = client.post(
        "/bots",
        json={
            "username": "room_bot",
            "emoji": "💬",
        },
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert bot_response.status_code == status.HTTP_201_CREATED
    bot_api_key = bot_response.json()["api_key"]

    # Send room message
    response = client.post(
        "/messages",
        json={"content": "Hello from bot!"},
        headers={"X-API-Key": bot_api_key},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["from_username"] == "room_bot"
    assert data["content"] == "Hello from bot!"
    assert data["message_type"] == "room"


def test_bot_cannot_send_direct_message(client: TestClient, registered_user: dict) -> None:
    """Test that bots cannot send direct messages."""
    username = registered_user["username"]

    # Create bot via /bots endpoint
    bot_response = client.post(
        "/bots",
        json={
            "username": "dm_bot",
            "emoji": "🚫",
        },
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert bot_response.status_code == status.HTTP_201_CREATED
    bot_api_key = bot_response.json()["api_key"]

    # Attempt to send direct message
    response = client.post(
        "/messages",
        json={"content": "Hello!", "to_username": username},
        headers={"X-API-Key": bot_api_key},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "does not have permission to send direct messages" in response.json()["detail"]


def test_bot_profile_includes_bot_and_emoji(client: TestClient, registered_user: dict) -> None:
    """Test that bot profile includes bot and emoji fields."""
    # Create bot via /bots endpoint
    bot_response = client.post(
        "/bots",
        json={
            "username": "profile_bot",
            "emoji": "👤",
        },
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert bot_response.status_code == status.HTTP_201_CREATED
    bot_api_key = bot_response.json()["api_key"]

    # Get profile
    response = client.get(
        "/users/me",
        headers={"X-API-Key": bot_api_key},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["username"] == "profile_bot"
    assert data["bot"] is True
    assert data["emoji"] == "👤"


def test_admin_can_update_bot_fields(
    client: TestClient, registered_user: dict
) -> None:
    """Test that admin can update bot and emoji fields."""
    # Register admin user
    admin_response = client.post(
        "/register",
        json={
            "username": "admin_user",
            "admin": True,
        },
    )
    admin_api_key = admin_response.json()["api_key"]

    # Register regular user
    user_response = client.post(
        "/register",
        json={
            "username": "regular_user",
            "bot": False,
        },
    )
    assert user_response.status_code == status.HTTP_201_CREATED

    # Admin updates user to bot
    response = client.patch(
        "/admin/users/regular_user",
        json={
            "bot": True,
            "emoji": "🔄",
        },
        headers={"X-API-Key": admin_api_key},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["username"] == "regular_user"
    assert data["bot"] is True
    assert data["emoji"] == "🔄"


def test_admin_get_all_users_includes_bot_fields(client: TestClient) -> None:
    """Test that admin endpoint returns bot and emoji fields."""
    # Register admin
    admin_response = client.post(
        "/register",
        json={
            "username": "admin_lister",
            "admin": True,
        },
    )
    admin_api_key = admin_response.json()["api_key"]

    # Create bot via /bots endpoint
    bot_response = client.post(
        "/bots",
        json={
            "username": "listed_bot",
            "emoji": "📋",
        },
        headers={"X-API-Key": admin_api_key},
    )
    assert bot_response.status_code == status.HTTP_201_CREATED

    # Get all users
    response = client.get(
        "/admin/users",
        headers={"X-API-Key": admin_api_key},
    )

    assert response.status_code == status.HTTP_200_OK
    users = response.json()
    bot_user = next(u for u in users if u["username"] == "listed_bot")
    assert bot_user["bot"] is True
    assert bot_user["emoji"] == "📋"


def test_admin_get_single_user_includes_bot_fields(client: TestClient) -> None:
    """Test that admin single user endpoint returns bot and emoji fields."""
    # Register admin
    admin_response = client.post(
        "/register",
        json={
            "username": "admin_getter",
            "admin": True,
        },
    )
    admin_api_key = admin_response.json()["api_key"]

    # Create bot via /bots endpoint
    bot_response = client.post(
        "/bots",
        json={
            "username": "single_bot",
            "emoji": "🔍",
        },
        headers={"X-API-Key": admin_api_key},
    )
    assert bot_response.status_code == status.HTTP_201_CREATED

    # Get single user
    response = client.get(
        "/admin/users/single_bot",
        headers={"X-API-Key": admin_api_key},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["username"] == "single_bot"
    assert data["bot"] is True
    assert data["emoji"] == "🔍"


def test_regular_user_has_default_bot_false(client: TestClient) -> None:
    """Test that regular users have bot=False by default."""
    response = client.post(
        "/register",
        json={
            "username": "human_user",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "human_user"
    assert data["bot"] is False
    assert data.get("emoji") is None


@pytest.mark.asyncio
async def test_bot_cannot_send_dm_via_websocket(client: TestClient, registered_user: dict) -> None:
    """Test that bots cannot send direct messages via WebSocket."""
    from unittest.mock import AsyncMock, patch

    from fastapi import WebSocketDisconnect

    from token_bowl_chat_server.models import User
    from token_bowl_chat_server.storage import storage

    # Create bot via /bots endpoint
    bot_response = client.post(
        "/bots",
        json={
            "username": "ws_bot",
            "emoji": "🔌",
        },
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert bot_response.status_code == status.HTTP_201_CREATED
    bot_api_key = bot_response.json()["api_key"]

    # Register target user
    target_response = client.post(
        "/register",
        json={
            "username": "target_user",
        },
    )
    assert target_response.status_code == status.HTTP_201_CREATED

    # Mock WebSocket authentication to return bot user
    bot_user = storage.get_user_by_api_key(bot_api_key)
    assert bot_user is not None
    assert bot_user.bot is True

    async def mock_websocket_auth(websocket):
        return bot_user

    mock_websocket = AsyncMock()
    # Set side_effect as a list: first call returns the message, second call raises disconnect
    mock_websocket.receive_json.side_effect = [
        {
            "type": "message",
            "content": "Hello!",
            "to_username": "target_user",
        },
        WebSocketDisconnect(),
    ]

    with patch("token_bowl_chat_server.api.websocket_auth", side_effect=mock_websocket_auth):
        from token_bowl_chat_server.api import websocket_endpoint

        with patch(
            "token_bowl_chat_server.api.connection_manager.connect"
        ) as mock_connect, patch(
            "token_bowl_chat_server.api.connection_manager.disconnect"
        ) as mock_disconnect:
            mock_connect.return_value = None
            mock_disconnect.return_value = None

            # Run the websocket endpoint (it will disconnect after message)
            await websocket_endpoint(mock_websocket)

            # Check that error was sent
            error_calls = [
                call
                for call in mock_websocket.send_json.call_args_list
                if len(call[0]) > 0 and call[0][0].get("type") == "error"
            ]
            assert len(error_calls) > 0
            error_message = error_calls[0][0][0]
            assert "does not have permission to send direct messages" in error_message["error"]


@pytest.mark.asyncio
async def test_bot_can_send_room_message_via_websocket(client: TestClient, registered_user: dict) -> None:
    """Test that bots can send room messages via WebSocket."""
    from unittest.mock import AsyncMock, patch

    from fastapi import WebSocketDisconnect

    from token_bowl_chat_server.models import User
    from token_bowl_chat_server.storage import storage

    # Create bot via /bots endpoint
    bot_response = client.post(
        "/bots",
        json={
            "username": "ws_room_bot",
            "emoji": "💬",
        },
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert bot_response.status_code == status.HTTP_201_CREATED
    bot_api_key = bot_response.json()["api_key"]

    # Get bot user
    bot_user = storage.get_user_by_api_key(bot_api_key)
    assert bot_user is not None
    assert bot_user.bot is True

    async def mock_websocket_auth(websocket):
        return bot_user

    mock_websocket = AsyncMock()
    # Set side_effect as a list: first call returns the message, second call raises disconnect
    mock_websocket.receive_json.side_effect = [
        {
            "type": "message",
            "content": "Hello room!",
        },
        WebSocketDisconnect(),
    ]

    with patch("token_bowl_chat_server.api.websocket_auth", side_effect=mock_websocket_auth):
        from token_bowl_chat_server.api import websocket_endpoint

        with patch(
            "token_bowl_chat_server.api.connection_manager.connect"
        ) as mock_connect, patch(
            "token_bowl_chat_server.api.connection_manager.disconnect"
        ) as mock_disconnect, patch(
            "token_bowl_chat_server.api.connection_manager.broadcast_to_room"
        ) as mock_broadcast:
            mock_connect.return_value = None
            mock_disconnect.return_value = None
            mock_broadcast.return_value = None

            # Run the websocket endpoint (it will disconnect after message)
            await websocket_endpoint(mock_websocket)

            # Check that message_sent confirmation was sent (not error)
            sent_calls = [
                call
                for call in mock_websocket.send_json.call_args_list
                if len(call[0]) > 0 and call[0][0].get("type") == "message_sent"
            ]
            assert len(sent_calls) > 0

            # Check that broadcast was called
            assert mock_broadcast.call_count > 0


def test_admin_setting_bot_true_clears_logo(client: TestClient) -> None:
    """Test that admin setting bot=true automatically clears any existing logo."""
    # Register admin user
    admin_response = client.post(
        "/register",
        json={
            "username": "admin_clear_logo",
            "admin": True,
        },
    )
    admin_api_key = admin_response.json()["api_key"]

    # Register regular user with a logo
    user_response = client.post(
        "/register",
        json={
            "username": "user_with_logo",
            "bot": False,
            "logo": "openai.png",
        },
    )
    assert user_response.status_code == status.HTTP_201_CREATED
    assert user_response.json()["logo"] == "openai.png"

    # Admin sets bot=true - should automatically clear the logo
    response = client.patch(
        "/admin/users/user_with_logo",
        json={
            "bot": True,
            "emoji": "🤖",
        },
        headers={"X-API-Key": admin_api_key},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["username"] == "user_with_logo"
    assert data["bot"] is True
    assert data["emoji"] == "🤖"
    assert data["logo"] is None  # Logo should be cleared


def test_admin_cannot_set_bot_true_with_logo(client: TestClient) -> None:
    """Test that admin cannot set both bot=true and logo in the same request."""
    # Register admin user
    admin_response = client.post(
        "/register",
        json={
            "username": "admin_bot_logo",
            "admin": True,
        },
    )
    admin_api_key = admin_response.json()["api_key"]

    # Register regular user
    user_response = client.post(
        "/register",
        json={
            "username": "user_bot_logo",
            "bot": False,
        },
    )
    assert user_response.status_code == status.HTTP_201_CREATED

    # Admin tries to set bot=true AND logo in same request - should fail
    response = client.patch(
        "/admin/users/user_bot_logo",
        json={
            "bot": True,
            "logo": "openai.png",
            "emoji": "🤖",
        },
        headers={"X-API-Key": admin_api_key},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Bots can only use emoji for avatars" in response.json()["detail"][0]["msg"]


# Bot ownership tests

def test_create_bot_via_bots_endpoint(client: TestClient, registered_user: dict) -> None:
    """Test creating a bot via POST /bots endpoint."""
    response = client.post(
        "/bots",
        json={
            "username": "my_bot",
            "emoji": "🤖",
            "webhook_url": "https://example.com/webhook",
        },
        headers={"X-API-Key": registered_user["api_key"]},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "my_bot"
    assert data["created_by"] == registered_user["username"]
    assert data["emoji"] == "🤖"
    assert data["webhook_url"] == "https://example.com/webhook"
    assert "api_key" in data


def test_get_my_bots(client: TestClient, registered_user: dict) -> None:
    """Test getting bots created by current user via GET /bots/me."""
    # Create two bots
    client.post(
        "/bots",
        json={"username": "bot1", "emoji": "🤖"},
        headers={"X-API-Key": registered_user["api_key"]},
    )
    client.post(
        "/bots",
        json={"username": "bot2", "emoji": "🦾"},
        headers={"X-API-Key": registered_user["api_key"]},
    )

    # Get my bots
    response = client.get(
        "/bots/me",
        headers={"X-API-Key": registered_user["api_key"]},
    )

    assert response.status_code == status.HTTP_200_OK
    bots = response.json()
    assert len(bots) == 2
    assert {bot["username"] for bot in bots} == {"bot1", "bot2"}
    assert all(bot["created_by"] == registered_user["username"] for bot in bots)


def test_update_bot(client: TestClient, registered_user: dict) -> None:
    """Test updating a bot via PATCH /bots/{bot_username}."""
    # Create bot
    create_response = client.post(
        "/bots",
        json={"username": "updateable_bot", "emoji": "🤖"},
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    # Update bot
    response = client.patch(
        "/bots/updateable_bot",
        json={
            "emoji": "🦿",
            "webhook_url": "https://example.com/new-webhook",
        },
        headers={"X-API-Key": registered_user["api_key"]},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["username"] == "updateable_bot"
    assert data["emoji"] == "🦿"
    assert data["webhook_url"] == "https://example.com/new-webhook"
    assert data["created_by"] == registered_user["username"]


def test_cannot_update_others_bot(client: TestClient, registered_user: dict, registered_user2: dict) -> None:
    """Test that users cannot update bots they don't own."""
    # User 1 creates a bot
    create_response = client.post(
        "/bots",
        json={"username": "user1_bot", "emoji": "🤖"},
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    # User 2 tries to update user 1's bot
    response = client.patch(
        "/bots/user1_bot",
        json={"emoji": "🦾"},
        headers={"X-API-Key": registered_user2["api_key"]},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "don't have permission to update bot" in response.json()["detail"]


def test_delete_bot(client: TestClient, registered_user: dict) -> None:
    """Test deleting a bot via DELETE /bots/{bot_username}."""
    # Create bot
    create_response = client.post(
        "/bots",
        json={"username": "deletable_bot", "emoji": "🤖"},
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    # Delete bot
    response = client.delete(
        "/bots/deletable_bot",
        headers={"X-API-Key": registered_user["api_key"]},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify bot is deleted
    get_response = client.get(
        "/bots/me",
        headers={"X-API-Key": registered_user["api_key"]},
    )
    bots = get_response.json()
    assert not any(bot["username"] == "deletable_bot" for bot in bots)


def test_cannot_delete_others_bot(client: TestClient, registered_user: dict, registered_user2: dict) -> None:
    """Test that users cannot delete bots they don't own."""
    # User 1 creates a bot
    create_response = client.post(
        "/bots",
        json={"username": "user1_bot_delete", "emoji": "🤖"},
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    # User 2 tries to delete user 1's bot
    response = client.delete(
        "/bots/user1_bot_delete",
        headers={"X-API-Key": registered_user2["api_key"]},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "don't have permission to delete bot" in response.json()["detail"]


def test_regenerate_bot_api_key(client: TestClient, registered_user: dict) -> None:
    """Test regenerating a bot's API key."""
    # Create bot
    create_response = client.post(
        "/bots",
        json={"username": "regen_bot", "emoji": "🤖"},
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    old_api_key = create_response.json()["api_key"]

    # Regenerate API key
    response = client.post(
        "/bots/regen_bot/regenerate-api-key",
        headers={"X-API-Key": registered_user["api_key"]},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "api_key" in data
    new_api_key = data["api_key"]
    assert new_api_key != old_api_key

    # Verify old key doesn't work
    old_key_response = client.get(
        "/users/me",
        headers={"X-API-Key": old_api_key},
    )
    assert old_key_response.status_code == status.HTTP_401_UNAUTHORIZED

    # Verify new key works
    new_key_response = client.get(
        "/users/me",
        headers={"X-API-Key": new_api_key},
    )
    assert new_key_response.status_code == status.HTTP_200_OK


def test_admin_can_update_any_bot(client: TestClient, registered_user: dict) -> None:
    """Test that admins can update any bot."""
    # Register admin
    admin_response = client.post(
        "/register",
        json={"username": "admin_bot_updater", "admin": True},
    )
    admin_api_key = admin_response.json()["api_key"]

    # User creates a bot
    create_response = client.post(
        "/bots",
        json={"username": "user_bot", "emoji": "🤖"},
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    # Admin updates the bot
    response = client.patch(
        "/bots/user_bot",
        json={"emoji": "🦾"},
        headers={"X-API-Key": admin_api_key},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["emoji"] == "🦾"


def test_admin_can_delete_any_bot(client: TestClient, registered_user: dict) -> None:
    """Test that admins can delete any bot."""
    # Register admin
    admin_response = client.post(
        "/register",
        json={"username": "admin_bot_deleter", "admin": True},
    )
    admin_api_key = admin_response.json()["api_key"]

    # User creates a bot
    create_response = client.post(
        "/bots",
        json={"username": "user_bot_delete", "emoji": "🤖"},
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    # Admin deletes the bot
    response = client.delete(
        "/bots/user_bot_delete",
        headers={"X-API-Key": admin_api_key},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
