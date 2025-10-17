"""Tests for API endpoints."""

import pytest
from unittest.mock import patch


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_register_user(client):
    """Test user registration."""
    response = client.post(
        "/register",
        json={"username": "new_user", "webhook_url": None},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "new_user"
    assert "api_key" in data
    assert len(data["api_key"]) == 64  # 32 bytes hex = 64 chars
    assert data["webhook_url"] is None


def test_register_user_with_webhook(client):
    """Test user registration with webhook URL."""
    response = client.post(
        "/register",
        json={"username": "webhook_user", "webhook_url": "https://example.com/webhook"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "webhook_user"
    assert data["webhook_url"] == "https://example.com/webhook"


def test_register_duplicate_username(client, registered_user):
    """Test that registering duplicate username fails."""
    response = client.post(
        "/register",
        json={"username": "test_user", "webhook_url": None},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_register_api_key_collision(client):
    """Test that API key collision is handled."""
    from token_bowl_chat_server import api as api_module

    # Mock storage.add_user to raise ValueError on first call (simulating API key collision)
    with patch.object(
        api_module.storage, "add_user", side_effect=ValueError("API key already exists")
    ):
        response = client.post(
            "/register",
            json={"username": "collision_user", "webhook_url": None},
        )
        assert response.status_code == 409
        assert "API key already exists" in response.json()["detail"]


def test_send_room_message(client, registered_user):
    """Test sending a room message."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.post(
        "/messages",
        json={"content": "Hello, room!"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["from_username"] == "test_user"
    assert data["content"] == "Hello, room!"
    assert data["message_type"] == "room"
    assert data["to_username"] is None


def test_send_direct_message(client, registered_user, registered_user2):
    """Test sending a direct message."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.post(
        "/messages",
        json={"content": "Private message", "to_username": "test_user2"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["from_username"] == "test_user"
    assert data["to_username"] == "test_user2"
    assert data["content"] == "Private message"
    assert data["message_type"] == "direct"


def test_send_message_without_auth(client):
    """Test that sending message without API key fails."""
    response = client.post(
        "/messages",
        json={"content": "Hello!"},
    )
    assert response.status_code == 401


def test_send_message_with_invalid_api_key(client):
    """Test that sending message with invalid API key fails."""
    headers = {"X-API-Key": "invalid_key"}
    response = client.post(
        "/messages",
        json={"content": "Hello!"},
        headers=headers,
    )
    assert response.status_code == 401


def test_send_direct_message_to_nonexistent_user(client, registered_user):
    """Test that sending direct message to nonexistent user fails."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.post(
        "/messages",
        json={"content": "Hello", "to_username": "nonexistent"},
        headers=headers,
    )
    assert response.status_code == 404


def test_get_messages(client, registered_user):
    """Test getting recent room messages."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # Send some messages
    for i in range(3):
        client.post(
            "/messages",
            json={"content": f"Message {i}"},
            headers=headers,
        )

    # Get messages
    response = client.get("/messages", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert "pagination" in data
    messages = data["messages"]
    assert len(messages) == 3
    assert messages[0]["content"] == "Message 0"
    assert messages[2]["content"] == "Message 2"
    assert data["pagination"]["total"] == 3
    assert data["pagination"]["offset"] == 0
    assert data["pagination"]["limit"] == 50
    assert data["pagination"]["has_more"] is False


def test_get_messages_with_limit(client, registered_user):
    """Test getting messages with limit."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # Send messages
    for i in range(5):
        client.post(
            "/messages",
            json={"content": f"Message {i}"},
            headers=headers,
        )

    # Get with limit
    response = client.get("/messages?limit=2", headers=headers)
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert len(messages) == 2
    # Should get the first 2 (offset=0, limit=2)
    assert messages[0]["content"] == "Message 0"
    assert messages[1]["content"] == "Message 1"
    assert data["pagination"]["total"] == 5
    assert data["pagination"]["has_more"] is True


def test_get_direct_messages(client, registered_user, registered_user2):
    """Test getting direct messages."""
    headers1 = {"X-API-Key": registered_user["api_key"]}
    headers2 = {"X-API-Key": registered_user2["api_key"]}

    # Send direct messages
    client.post(
        "/messages",
        json={"content": "DM 1", "to_username": "test_user2"},
        headers=headers1,
    )
    client.post(
        "/messages",
        json={"content": "DM 2", "to_username": "test_user"},
        headers=headers2,
    )

    # Get direct messages for user 1
    response = client.get("/messages/direct", headers=headers1)
    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert "pagination" in data
    messages = data["messages"]
    assert len(messages) == 2
    assert all(
        msg["from_username"] in ["test_user", "test_user2"]
        and msg["to_username"] in ["test_user", "test_user2"]
        for msg in messages
    )
    assert data["pagination"]["total"] == 2


def test_get_messages_with_pagination(client, registered_user):
    """Test pagination with offset and limit."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # Send 10 messages
    for i in range(10):
        client.post(
            "/messages",
            json={"content": f"Message {i}"},
            headers=headers,
        )

    # Get first page (offset=0, limit=3)
    response = client.get("/messages?offset=0&limit=3", headers=headers)
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert len(messages) == 3
    assert messages[0]["content"] == "Message 0"
    assert messages[2]["content"] == "Message 2"
    assert data["pagination"]["total"] == 10
    assert data["pagination"]["offset"] == 0
    assert data["pagination"]["limit"] == 3
    assert data["pagination"]["has_more"] is True

    # Get second page (offset=3, limit=3)
    response = client.get("/messages?offset=3&limit=3", headers=headers)
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert len(messages) == 3
    assert messages[0]["content"] == "Message 3"
    assert messages[2]["content"] == "Message 5"
    assert data["pagination"]["offset"] == 3
    assert data["pagination"]["has_more"] is True

    # Get last page (offset=9, limit=3)
    response = client.get("/messages?offset=9&limit=3", headers=headers)
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert len(messages) == 1  # Only 1 message left
    assert messages[0]["content"] == "Message 9"
    assert data["pagination"]["offset"] == 9
    assert data["pagination"]["has_more"] is False


def test_get_direct_messages_with_pagination(client, registered_user, registered_user2):
    """Test pagination for direct messages."""
    headers1 = {"X-API-Key": registered_user["api_key"]}
    headers2 = {"X-API-Key": registered_user2["api_key"]}

    # Send 5 direct messages
    for i in range(5):
        client.post(
            "/messages",
            json={"content": f"DM {i}", "to_username": "test_user2"},
            headers=headers1,
        )

    # Get first page for user 2
    response = client.get("/messages/direct?offset=0&limit=2", headers=headers2)
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert len(messages) == 2
    assert messages[0]["content"] == "DM 0"
    assert messages[1]["content"] == "DM 1"
    assert data["pagination"]["total"] == 5
    assert data["pagination"]["has_more"] is True

    # Get next page
    response = client.get("/messages/direct?offset=2&limit=2", headers=headers2)
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert len(messages) == 2
    assert messages[0]["content"] == "DM 2"
    assert data["pagination"]["has_more"] is True


def test_get_users(client, registered_user, registered_user2):
    """Test getting list of users."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/users", headers=headers)
    assert response.status_code == 200
    users = response.json()
    assert "test_user" in users
    assert "test_user2" in users


def test_get_online_users(client, registered_user):
    """Test getting list of online users."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/users/online", headers=headers)
    assert response.status_code == 200
    online_users = response.json()
    assert isinstance(online_users, list)
    # No users are online via WebSocket yet
    assert len(online_users) == 0


def test_get_messages_with_invalid_since(client, registered_user):
    """Test getting messages with invalid since timestamp."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/messages?since=invalid_timestamp", headers=headers)
    assert response.status_code == 400
    assert "Invalid timestamp format" in response.json()["detail"]


def test_get_direct_messages_with_invalid_since(client, registered_user):
    """Test getting direct messages with invalid since timestamp."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/messages/direct?since=not_a_date", headers=headers)
    assert response.status_code == 400
    assert "Invalid timestamp format" in response.json()["detail"]


def test_websocket_send_room_message(client, registered_user):
    """Test sending a room message via WebSocket."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Send a room message
        websocket.send_json({"content": "Hello from WebSocket!"})

        # Receive confirmation
        data = websocket.receive_json()
        assert data["status"] == "sent"
        assert data["message"]["content"] == "Hello from WebSocket!"
        assert data["message"]["from_username"] == "test_user"
        assert data["message"]["message_type"] == "room"


def test_websocket_send_direct_message(client, registered_user, registered_user2):
    """Test sending a direct message via WebSocket."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Send a direct message
        websocket.send_json({"content": "Private WebSocket message", "to_username": "test_user2"})

        # Receive confirmation
        data = websocket.receive_json()
        assert data["status"] == "sent"
        assert data["message"]["content"] == "Private WebSocket message"
        assert data["message"]["from_username"] == "test_user"
        assert data["message"]["to_username"] == "test_user2"
        assert data["message"]["message_type"] == "direct"


def test_websocket_missing_content(client, registered_user):
    """Test WebSocket with missing content field."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Send message without content
        websocket.send_json({"to_username": "test_user2"})

        # Should receive error
        data = websocket.receive_json()
        assert "error" in data
        assert "Missing content field" in data["error"]


def test_websocket_nonexistent_recipient(client, registered_user):
    """Test WebSocket direct message to nonexistent user."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Send message to nonexistent user
        websocket.send_json({"content": "Hello", "to_username": "nonexistent"})

        # Should receive error
        data = websocket.receive_json()
        assert "error" in data
        assert "not found" in data["error"]


def test_websocket_receive_room_message(client, registered_user, registered_user2):
    """Test receiving room messages via WebSocket."""
    # Connect both users via WebSocket
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as ws1:
        with client.websocket_connect(f"/ws?api_key={registered_user2['api_key']}") as ws2:
            # User 1 sends a room message
            ws1.send_json({"content": "Broadcast message"})

            # User 1 gets confirmation
            data1 = ws1.receive_json()
            assert data1["status"] == "sent"

            # User 2 should receive the message
            data2 = ws2.receive_json()
            assert data2["content"] == "Broadcast message"
            assert data2["from_username"] == "test_user"
            assert data2["message_type"] == "room"


def test_websocket_receive_direct_message(client, registered_user, registered_user2):
    """Test receiving direct messages via WebSocket."""
    # Connect both users via WebSocket
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as ws1:
        with client.websocket_connect(f"/ws?api_key={registered_user2['api_key']}") as ws2:
            # User 1 sends a direct message to user 2
            ws1.send_json({"content": "Direct WebSocket message", "to_username": "test_user2"})

            # User 1 gets confirmation
            data1 = ws1.receive_json()
            assert data1["status"] == "sent"

            # User 2 should receive the message
            data2 = ws2.receive_json()
            assert data2["content"] == "Direct WebSocket message"
            assert data2["from_username"] == "test_user"
            assert data2["to_username"] == "test_user2"
            assert data2["message_type"] == "direct"


def test_websocket_invalid_api_key(client):
    """Test WebSocket connection with invalid API key."""
    from fastapi import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?api_key=invalid_key") as websocket:
            pass


def test_websocket_missing_api_key(client):
    """Test WebSocket connection without API key."""
    from fastapi import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws") as websocket:
            pass


def test_register_user_with_logo(client):
    """Test user registration with a logo."""
    response = client.post(
        "/register",
        json={"username": "logo_user", "webhook_url": None, "logo": "claude-color.png"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "logo_user"
    assert data["logo"] == "claude-color.png"


def test_register_user_with_invalid_logo(client):
    """Test user registration with an invalid logo."""
    response = client.post(
        "/register",
        json={"username": "invalid_logo_user", "webhook_url": None, "logo": "invalid.png"},
    )
    assert response.status_code == 422  # Validation error


def test_get_available_logos(client, registered_user):
    """Test getting list of available logos."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/logos", headers=headers)
    assert response.status_code == 200
    logos = response.json()
    assert isinstance(logos, list)
    assert len(logos) > 0
    assert "claude-color.png" in logos
    assert "openai.png" in logos


def test_update_user_logo(client, registered_user):
    """Test updating a user's logo."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.patch(
        "/users/me/logo",
        json={"logo": "gemini-color.png"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Logo updated successfully"
    assert data["logo"] == "gemini-color.png"


def test_update_user_logo_with_invalid_logo(client, registered_user):
    """Test updating a user's logo with an invalid logo."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.patch(
        "/users/me/logo",
        json={"logo": "nonexistent.png"},
        headers=headers,
    )
    assert response.status_code == 422  # Validation error


def test_clear_user_logo(client, registered_user):
    """Test clearing a user's logo."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # First set a logo
    client.patch(
        "/users/me/logo",
        json={"logo": "grok.png"},
        headers=headers,
    )

    # Then clear it
    response = client.patch(
        "/users/me/logo",
        json={"logo": None},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Logo updated successfully"
    assert data["logo"] == ""


def test_update_logo_without_auth(client):
    """Test updating logo without authentication."""
    response = client.patch(
        "/users/me/logo",
        json={"logo": "claude-color.png"},
    )
    assert response.status_code == 401
