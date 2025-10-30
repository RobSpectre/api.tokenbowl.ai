"""Tests for API endpoints."""

from unittest.mock import patch

import pytest


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
    assert messages[0]["content"] == "Message 2"
    assert messages[2]["content"] == "Message 0"
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
    # Should get the most recent 2 (offset=0, limit=2)
    assert messages[0]["content"] == "Message 4"
    assert messages[1]["content"] == "Message 3"
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

    # Get first page (offset=0, limit=3) - newest first
    response = client.get("/messages?offset=0&limit=3", headers=headers)
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert len(messages) == 3
    assert messages[0]["content"] == "Message 9"
    assert messages[2]["content"] == "Message 7"
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
    assert messages[0]["content"] == "Message 6"
    assert messages[2]["content"] == "Message 4"
    assert data["pagination"]["offset"] == 3
    assert data["pagination"]["has_more"] is True

    # Get last page (offset=9, limit=3)
    response = client.get("/messages?offset=9&limit=3", headers=headers)
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert len(messages) == 1  # Only 1 message left
    assert messages[0]["content"] == "Message 0"
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

    # Get first page for user 2 - newest first
    response = client.get("/messages/direct?offset=0&limit=2", headers=headers2)
    assert response.status_code == 200
    data = response.json()
    messages = data["messages"]
    assert len(messages) == 2
    assert messages[0]["content"] == "DM 4"
    assert messages[1]["content"] == "DM 3"
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
    usernames = [user["username"] for user in users]
    assert "test_user" in usernames
    assert "test_user2" in usernames
    # Verify structure includes display info
    assert all("username" in user for user in users)
    assert all("logo" in user for user in users)
    assert all("emoji" in user for user in users)
    assert all("bot" in user for user in users)
    assert all("viewer" in user for user in users)


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
    with (
        client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as ws1,
        client.websocket_connect(f"/ws?api_key={registered_user2['api_key']}") as ws2,
    ):
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
    with (
        client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as ws1,
        client.websocket_connect(f"/ws?api_key={registered_user2['api_key']}") as ws2,
    ):
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

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws?api_key=invalid_key"):
        pass


def test_websocket_missing_api_key(client):
    """Test WebSocket connection without API key."""
    from fastapi import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws"):
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


def test_get_available_logos(client):
    """Test getting list of available logos (public endpoint)."""
    response = client.get("/logos")
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


def test_update_user_webhook(client, registered_user):
    """Test updating a user's webhook URL."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.patch(
        "/users/me/webhook",
        json={"webhook_url": "https://example.com/new-webhook"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Webhook URL updated successfully"
    assert data["webhook_url"] == "https://example.com/new-webhook"

    # Verify via profile endpoint
    profile = client.get("/users/me", headers=headers)
    assert profile.json()["webhook_url"] == "https://example.com/new-webhook"


def test_clear_user_webhook(client, registered_user):
    """Test clearing a user's webhook URL."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # First set a webhook
    client.patch(
        "/users/me/webhook",
        json={"webhook_url": "https://example.com/webhook"},
        headers=headers,
    )

    # Then clear it
    response = client.patch(
        "/users/me/webhook",
        json={"webhook_url": None},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Webhook URL updated successfully"
    assert data["webhook_url"] == ""

    # Verify via profile endpoint
    profile = client.get("/users/me", headers=headers)
    assert profile.json()["webhook_url"] is None


def test_update_webhook_with_invalid_url(client, registered_user):
    """Test updating webhook with invalid URL."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.patch(
        "/users/me/webhook",
        json={"webhook_url": "not-a-valid-url"},
        headers=headers,
    )
    assert response.status_code == 422  # Validation error


def test_update_webhook_without_auth(client):
    """Test updating webhook without authentication."""
    response = client.patch(
        "/users/me/webhook",
        json={"webhook_url": "https://example.com/webhook"},
    )
    assert response.status_code == 401


def test_get_my_profile(client, registered_user):
    """Test getting current user's profile."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/users/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "test_user"
    assert data["api_key"] == registered_user["api_key"]
    assert data["email"] is None  # No email for regular registration
    assert "created_at" in data


def test_get_my_profile_without_auth(client):
    """Test getting profile without authentication."""
    response = client.get("/users/me")
    assert response.status_code == 401


def test_update_my_username(client, registered_user):
    """Test updating current user's username."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.patch(
        "/users/me/username",
        json={"username": "new_username"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "new_username"
    assert data["api_key"] == registered_user["api_key"]

    # Verify old username no longer works
    old_user = client.get("/users/me", headers=headers)
    # Should still work because API key is the same
    assert old_user.status_code == 200
    assert old_user.json()["username"] == "new_username"


def test_update_my_username_to_existing(client, registered_user, registered_user2):
    """Test updating username to one that already exists."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.patch(
        "/users/me/username",
        json={"username": "test_user2"},  # Already exists
        headers=headers,
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_update_my_username_without_auth(client):
    """Test updating username without authentication."""
    response = client.patch(
        "/users/me/username",
        json={"username": "new_username"},
    )
    assert response.status_code == 401


def test_regenerate_api_key(client, registered_user):
    """Test regenerating API key."""
    headers = {"X-API-Key": registered_user["api_key"]}
    old_api_key = registered_user["api_key"]

    response = client.post("/users/me/regenerate-api-key", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "API key regenerated successfully"
    assert "api_key" in data
    assert len(data["api_key"]) == 64  # 32 bytes hex = 64 chars
    new_api_key = data["api_key"]

    # Verify new API key is different from old one
    assert new_api_key != old_api_key

    # Verify old API key no longer works
    old_headers = {"X-API-Key": old_api_key}
    response = client.get("/users/me", headers=old_headers)
    assert response.status_code == 401

    # Verify new API key works
    new_headers = {"X-API-Key": new_api_key}
    response = client.get("/users/me", headers=new_headers)
    assert response.status_code == 200
    assert response.json()["username"] == "test_user"
    assert response.json()["api_key"] == new_api_key


def test_regenerate_api_key_without_auth(client):
    """Test regenerating API key without authentication."""
    response = client.post("/users/me/regenerate-api-key")
    assert response.status_code == 401


# Admin functionality tests


def test_register_admin_user(client):
    """Test registering a user with admin privileges."""
    response = client.post(
        "/register",
        json={"username": "admin_test", "webhook_url": None, "admin": True},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "admin_test"
    assert data["admin"] is True


def test_admin_list_all_users(client, registered_user, registered_user2, registered_admin):
    """Test admin listing all users."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.get("/admin/users", headers=headers)
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert len(users) == 3  # test_user, test_user2, admin_user
    usernames = [user["username"] for user in users]
    assert "test_user" in usernames
    assert "test_user2" in usernames
    assert "admin_user" in usernames


def test_admin_list_all_users_without_admin(client, registered_user):
    """Test non-admin user cannot list all users."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/admin/users", headers=headers)
    assert response.status_code == 403
    assert "Admin privileges required" in response.json()["detail"]


def test_admin_get_user(client, registered_user, registered_admin):
    """Test admin getting a specific user's profile."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.get(f"/admin/users/{registered_user['id']}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "test_user"
    assert data["api_key"] == registered_user["api_key"]
    assert "created_at" in data
    assert data["admin"] is False


def test_admin_get_user_not_found(client, registered_admin):
    """Test admin getting a nonexistent user."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.get("/admin/users/00000000-0000-0000-0000-000000000000", headers=headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_admin_get_user_without_admin(client, registered_user):
    """Test non-admin user cannot get user details."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get(f"/admin/users/{registered_user['id']}", headers=headers)
    assert response.status_code == 403


def test_admin_update_user(client, registered_user, registered_admin):
    """Test admin updating a user's profile."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.patch(
        f"/admin/users/{registered_user['id']}",
        json={
            "email": "newemail@example.com",
            "webhook_url": "https://example.com/webhook",
            "logo": "claude-color.png",
            "viewer": True,
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "test_user"
    assert data["email"] == "newemail@example.com"
    assert data["webhook_url"] == "https://example.com/webhook"
    assert data["logo"] == "claude-color.png"
    assert data["viewer"] is True


def test_admin_update_user_admin_status(client, registered_user, registered_admin):
    """Test admin changing a user's admin status."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.patch(
        f"/admin/users/{registered_user['id']}",
        json={"admin": True},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["admin"] is True


def test_admin_update_user_not_found(client, registered_admin):
    """Test admin updating a nonexistent user."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.patch(
        "/admin/users/00000000-0000-0000-0000-000000000000",
        json={"email": "test@example.com"},
        headers=headers,
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_admin_update_user_without_admin(client, registered_user, registered_user2):
    """Test non-admin user cannot update other users."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.patch(
        f"/admin/users/{registered_user2['id']}",
        json={"email": "test@example.com"},
        headers=headers,
    )
    assert response.status_code == 403


def test_admin_delete_user(client, registered_user, registered_admin):
    """Test admin deleting a user."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    user_id = registered_user["id"]
    response = client.delete(f"/admin/users/{user_id}", headers=headers)
    assert response.status_code == 204

    # Verify user is deleted
    response = client.get(f"/admin/users/{user_id}", headers=headers)
    assert response.status_code == 404


def test_admin_delete_user_not_found(client, registered_admin):
    """Test admin deleting a nonexistent user."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.delete("/admin/users/00000000-0000-0000-0000-000000000000", headers=headers)
    assert response.status_code == 404


def test_admin_delete_user_without_admin(client, registered_user, registered_user2):
    """Test non-admin user cannot delete users."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.delete(f"/admin/users/{registered_user2['id']}", headers=headers)
    assert response.status_code == 403


def test_admin_get_message(client, registered_user, registered_admin):
    """Test admin getting a message by ID."""
    # First, send a message
    headers = {"X-API-Key": registered_user["api_key"]}
    msg_response = client.post(
        "/messages",
        json={"content": "Test message for admin"},
        headers=headers,
    )
    assert msg_response.status_code == 201
    message_id = msg_response.json()["id"]

    # Now retrieve it as admin
    admin_headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.get(f"/admin/messages/{message_id}", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == message_id
    assert data["content"] == "Test message for admin"
    assert data["from_username"] == "test_user"


def test_admin_get_message_not_found(client, registered_admin):
    """Test admin getting a nonexistent message."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/admin/messages/{fake_uuid}", headers=headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_admin_get_message_without_admin(client, registered_user):
    """Test non-admin user cannot get messages by ID."""
    headers = {"X-API-Key": registered_user["api_key"]}
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/admin/messages/{fake_uuid}", headers=headers)
    assert response.status_code == 403


def test_admin_update_message(client, registered_user, registered_admin):
    """Test admin updating a message's content."""
    # First, send a message
    headers = {"X-API-Key": registered_user["api_key"]}
    msg_response = client.post(
        "/messages",
        json={"content": "Original content"},
        headers=headers,
    )
    assert msg_response.status_code == 201
    message_id = msg_response.json()["id"]

    # Update it as admin
    admin_headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.patch(
        f"/admin/messages/{message_id}",
        json={"content": "Moderated content"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == message_id
    assert data["content"] == "Moderated content"
    assert data["from_username"] == "test_user"


def test_admin_update_message_not_found(client, registered_admin):
    """Test admin updating a nonexistent message."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.patch(
        f"/admin/messages/{fake_uuid}",
        json={"content": "New content"},
        headers=headers,
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_admin_update_message_without_admin(client, registered_user):
    """Test non-admin user cannot update messages."""
    headers = {"X-API-Key": registered_user["api_key"]}
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.patch(
        f"/admin/messages/{fake_uuid}",
        json={"content": "New content"},
        headers=headers,
    )
    assert response.status_code == 403


def test_admin_delete_message(client, registered_user, registered_admin):
    """Test admin deleting a message."""
    # First, send a message
    headers = {"X-API-Key": registered_user["api_key"]}
    msg_response = client.post(
        "/messages",
        json={"content": "Message to be deleted"},
        headers=headers,
    )
    assert msg_response.status_code == 201
    message_id = msg_response.json()["id"]

    # Delete it as admin
    admin_headers = {"X-API-Key": registered_admin["api_key"]}
    response = client.delete(f"/admin/messages/{message_id}", headers=admin_headers)
    assert response.status_code == 204

    # Verify it's deleted
    response = client.get(f"/admin/messages/{message_id}", headers=admin_headers)
    assert response.status_code == 404


def test_admin_delete_message_not_found(client, registered_admin):
    """Test admin deleting a nonexistent message."""
    headers = {"X-API-Key": registered_admin["api_key"]}
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.delete(f"/admin/messages/{fake_uuid}", headers=headers)
    assert response.status_code == 404


def test_admin_delete_message_without_admin(client, registered_user):
    """Test non-admin user cannot delete messages."""
    headers = {"X-API-Key": registered_user["api_key"]}
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = client.delete(f"/admin/messages/{fake_uuid}", headers=headers)
    assert response.status_code == 403


def test_admin_delete_message_websocket(client, registered_user, registered_admin):
    """Test admin can delete any message via WebSocket."""
    user_api_key = registered_user["api_key"]
    admin_api_key = registered_admin["api_key"]

    # User sends a message
    response = client.post(
        "/messages",
        json={"content": "Test message to be deleted"},
        headers={"X-API-Key": user_api_key},
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    # Admin deletes the message via WebSocket
    with client.websocket_connect(f"/ws?api_key={admin_api_key}") as websocket:
        websocket.send_json(
            {
                "type": "delete_message",
                "message_id": message_id,
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "message_deleted"
        assert response["message_id"] == message_id

    # Verify the message was deleted by trying to get messages
    response = client.get("/messages", headers={"X-API-Key": user_api_key})
    assert response.status_code == 200
    messages = response.json()["messages"]
    # The message should not be in the list
    message_ids = [msg["id"] for msg in messages]
    assert message_id not in message_ids


def test_admin_delete_message_websocket_not_found(client, registered_admin):
    """Test admin gets error when deleting non-existent message via WebSocket."""
    admin_api_key = registered_admin["api_key"]
    fake_uuid = "00000000-0000-0000-0000-000000000000"

    with client.websocket_connect(f"/ws?api_key={admin_api_key}") as websocket:
        websocket.send_json(
            {
                "type": "delete_message",
                "message_id": fake_uuid,
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "error"
        assert "not found" in response["error"].lower()


def test_admin_delete_message_websocket_missing_id(client, registered_admin):
    """Test admin gets error when message_id is missing via WebSocket."""
    admin_api_key = registered_admin["api_key"]

    with client.websocket_connect(f"/ws?api_key={admin_api_key}") as websocket:
        websocket.send_json(
            {
                "type": "delete_message",
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "error"
        assert "missing" in response["error"].lower()


def test_non_admin_cannot_delete_message_websocket(client, registered_user):
    """Test non-admin user cannot delete messages via WebSocket."""
    user_api_key = registered_user["api_key"]

    # User sends a message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": user_api_key},
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    # User tries to delete via WebSocket (should fail)
    with client.websocket_connect(f"/ws?api_key={user_api_key}") as websocket:
        websocket.send_json(
            {
                "type": "delete_message",
                "message_id": message_id,
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "error"
        assert "admin" in response["error"].lower()


def test_get_user_profile(client, registered_user, registered_user2):
    """Test getting a public user profile."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # Get the other user's profile
    response = client.get(f"/users/{registered_user2['id']}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == registered_user2["username"]
    assert "logo" in data
    assert "emoji" in data
    assert "bot" in data
    assert "viewer" in data

    # Should NOT include sensitive data
    assert "api_key" not in data
    assert "email" not in data
    assert "webhook_url" not in data
    assert "created_at" not in data


def test_get_user_profile_not_found(client, registered_user):
    """Test getting a profile for non-existent user."""
    headers = {"X-API-Key": registered_user["api_key"]}

    response = client.get("/users/00000000-0000-0000-0000-000000000000", headers=headers)

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_user_profile_with_logo_and_emoji(client, registered_user):
    """Test getting profile of user with logo and emoji."""
    # Create a bot with emoji via /bots endpoint
    bot_response = client.post(
        "/bots",
        json={
            "username": "test_bot",
            "emoji": "🤖",
        },
        headers={"X-API-Key": registered_user["api_key"]},
    )
    assert bot_response.status_code == 201
    bot_data = bot_response.json()
    bot_api_key = bot_data["api_key"]
    bot_id = bot_data["id"]

    # Register a regular user with logo
    user_response = client.post(
        "/register",
        json={
            "username": "logo_user",
            "logo": "openai.png",
        },
    )
    user_data = user_response.json()
    user_api_key = user_data["api_key"]
    user_id = user_data["id"]

    # Bot gets user profile
    response = client.get(
        f"/users/{user_id}",
        headers={"X-API-Key": bot_api_key},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "logo_user"
    assert data["logo"] == "openai.png"
    assert data["emoji"] is None
    assert data["bot"] is False
    assert data["viewer"] is False

    # User gets bot profile
    response = client.get(
        f"/users/{bot_id}",
        headers={"X-API-Key": user_api_key},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "test_bot"
    assert data["logo"] is None
    assert data["emoji"] == "🤖"
    assert data["bot"] is True
    assert data["viewer"] is False


def test_get_user_profile_viewer(client, registered_user):
    """Test getting profile of a viewer user."""
    # Register a viewer
    viewer_response = client.post(
        "/register",
        json={
            "username": "viewer_user",
            "viewer": True,
        },
    )
    viewer_id = viewer_response.json()["id"]

    # Get viewer profile
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get(f"/users/{viewer_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "viewer_user"
    assert data["viewer"] is True
    assert data["bot"] is False


def test_get_user_profile_requires_auth(client):
    """Test that getting user profile requires authentication."""
    response = client.get("/users/someuser")

    assert response.status_code == 401


# WebSocket message history and user discovery tests


def test_websocket_get_messages(client, registered_user):
    """Test getting room message history via WebSocket."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # Send some room messages first
    for i in range(5):
        client.post(
            "/messages",
            json={"content": f"Room message {i}"},
            headers=headers,
        )

    # Connect via WebSocket and request message history
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Request all messages
        websocket.send_json({"type": "get_messages"})

        # Receive response
        data = websocket.receive_json()
        assert data["type"] == "messages"
        assert "messages" in data
        assert "pagination" in data
        assert len(data["messages"]) == 5
        assert data["pagination"]["total"] == 5
        assert data["pagination"]["offset"] == 0
        assert data["pagination"]["limit"] == 50
        assert data["pagination"]["has_more"] is False

        # Verify message structure includes display info
        for msg in data["messages"]:
            assert "from_username" in msg
            assert "from_user_logo" in msg
            assert "from_user_emoji" in msg
            assert "from_user_bot" in msg


def test_websocket_get_messages_with_pagination(client, registered_user):
    """Test getting room messages with pagination via WebSocket."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # Send 10 room messages
    for i in range(10):
        client.post(
            "/messages",
            json={"content": f"Message {i}"},
            headers=headers,
        )

    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Request first page - newest first
        websocket.send_json({"type": "get_messages", "limit": 3, "offset": 0})
        data = websocket.receive_json()

        assert data["type"] == "messages"
        assert len(data["messages"]) == 3
        assert data["messages"][0]["content"] == "Message 9"
        assert data["messages"][2]["content"] == "Message 7"
        assert data["pagination"]["total"] == 10
        assert data["pagination"]["offset"] == 0
        assert data["pagination"]["limit"] == 3
        assert data["pagination"]["has_more"] is True

        # Request second page
        websocket.send_json({"type": "get_messages", "limit": 3, "offset": 3})
        data = websocket.receive_json()

        assert len(data["messages"]) == 3
        assert data["messages"][0]["content"] == "Message 6"
        assert data["pagination"]["offset"] == 3
        assert data["pagination"]["has_more"] is True


def test_websocket_get_messages_with_since(client, registered_user):
    """Test getting room messages with since timestamp via WebSocket."""
    from datetime import UTC, datetime

    headers = {"X-API-Key": registered_user["api_key"]}

    # Send some messages
    client.post("/messages", json={"content": "Old message 1"}, headers=headers)
    client.post("/messages", json={"content": "Old message 2"}, headers=headers)

    # Get current time for since parameter
    since_time = datetime.now(UTC)

    # Send more messages after the timestamp
    client.post("/messages", json={"content": "New message 1"}, headers=headers)
    client.post("/messages", json={"content": "New message 2"}, headers=headers)

    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Request messages since timestamp
        websocket.send_json({"type": "get_messages", "since": since_time.isoformat()})

        data = websocket.receive_json()
        assert data["type"] == "messages"
        # Should only get the 2 new messages
        assert len(data["messages"]) >= 2
        contents = [msg["content"] for msg in data["messages"]]
        assert "New message 1" in contents
        assert "New message 2" in contents


def test_websocket_get_messages_invalid_since(client, registered_user):
    """Test getting messages with invalid since timestamp via WebSocket."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Request messages with invalid timestamp
        websocket.send_json({"type": "get_messages", "since": "invalid_timestamp"})

        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "Invalid timestamp format" in data["error"]


def test_websocket_get_direct_messages(client, registered_user, registered_user2):
    """Test getting direct message history via WebSocket."""
    headers1 = {"X-API-Key": registered_user["api_key"]}
    headers2 = {"X-API-Key": registered_user2["api_key"]}

    # Send some direct messages
    client.post(
        "/messages",
        json={"content": "DM 1 to user2", "to_username": "test_user2"},
        headers=headers1,
    )
    client.post(
        "/messages",
        json={"content": "DM 2 to user1", "to_username": "test_user"},
        headers=headers2,
    )
    client.post(
        "/messages",
        json={"content": "DM 3 to user2", "to_username": "test_user2"},
        headers=headers1,
    )

    # User 1 gets their direct messages
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        websocket.send_json({"type": "get_direct_messages"})

        data = websocket.receive_json()
        assert data["type"] == "direct_messages"
        assert "messages" in data
        assert "pagination" in data
        assert len(data["messages"]) == 3

        # All messages should involve user1
        for msg in data["messages"]:
            assert msg["from_username"] in ["test_user", "test_user2"]
            assert msg["to_username"] in ["test_user", "test_user2"]
            assert msg["message_type"] == "direct"


def test_websocket_get_direct_messages_with_pagination(client, registered_user, registered_user2):
    """Test getting direct messages with pagination via WebSocket."""
    headers1 = {"X-API-Key": registered_user["api_key"]}

    # Send 5 direct messages
    for i in range(5):
        client.post(
            "/messages",
            json={"content": f"DM {i}", "to_username": "test_user2"},
            headers=headers1,
        )

    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Request first page
        websocket.send_json({"type": "get_direct_messages", "limit": 2, "offset": 0})
        data = websocket.receive_json()

        assert data["type"] == "direct_messages"
        assert len(data["messages"]) == 2
        assert data["pagination"]["total"] == 5
        assert data["pagination"]["has_more"] is True


def test_websocket_get_unread_messages(client, registered_user, registered_user2):
    """Test getting unread room messages via WebSocket."""
    headers = {"X-API-Key": registered_user2["api_key"]}

    # User 2 sends room messages
    for i in range(3):
        client.post(
            "/messages",
            json={"content": f"Unread room message {i}"},
            headers=headers,
        )

    # User 1 gets unread messages (hasn't marked any as read)
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        websocket.send_json({"type": "get_unread_messages"})

        data = websocket.receive_json()
        assert data["type"] == "unread_messages"
        assert "messages" in data
        assert len(data["messages"]) >= 3


def test_websocket_get_unread_direct_messages(client, registered_user, registered_user2):
    """Test getting unread direct messages via WebSocket."""
    headers2 = {"X-API-Key": registered_user2["api_key"]}

    # User 2 sends DMs to user 1
    for i in range(3):
        client.post(
            "/messages",
            json={"content": f"Unread DM {i}", "to_username": "test_user"},
            headers=headers2,
        )

    # User 1 gets unread DMs
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        websocket.send_json({"type": "get_unread_direct_messages"})

        data = websocket.receive_json()
        assert data["type"] == "unread_direct_messages"
        assert "messages" in data
        assert len(data["messages"]) >= 3

        # All should be DMs to user1
        for msg in data["messages"]:
            assert msg["to_username"] == "test_user"
            assert msg["message_type"] == "direct"


def test_websocket_get_users(client, registered_user, registered_user2):
    """Test getting all users via WebSocket."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        websocket.send_json({"type": "get_users"})

        data = websocket.receive_json()
        assert data["type"] == "users"
        assert "users" in data
        assert isinstance(data["users"], list)
        assert len(data["users"]) >= 2

        # Verify structure
        usernames = [user["username"] for user in data["users"]]
        assert "test_user" in usernames
        assert "test_user2" in usernames

        # Verify all users have required fields
        for user in data["users"]:
            assert "username" in user
            assert "logo" in user
            assert "emoji" in user
            assert "bot" in user
            assert "viewer" in user


def test_websocket_get_online_users(client, registered_user, registered_user2):
    """Test getting online users via WebSocket."""
    # Connect user2 via WebSocket
    with (
        client.websocket_connect(f"/ws?api_key={registered_user2['api_key']}"),
        client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as ws1,
    ):
        # User1 requests online users
        ws1.send_json({"type": "get_online_users"})

        data = ws1.receive_json()
        assert data["type"] == "online_users"
        assert "users" in data
        assert isinstance(data["users"], list)

        # Both users should be online
        usernames = [user["username"] for user in data["users"]]
        assert "test_user" in usernames
        assert "test_user2" in usernames

        # Verify structure
        for user in data["users"]:
            assert "username" in user
            assert "logo" in user
            assert "emoji" in user
            assert "bot" in user
            assert "viewer" in user


def test_websocket_get_user_profile(client, registered_user, registered_user2):
    """Test getting user profile via WebSocket."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Request user2's profile
        websocket.send_json({"type": "get_user_profile", "username": "test_user2"})

        data = websocket.receive_json()
        assert data["type"] == "user_profile"
        assert "user" in data
        assert data["user"]["username"] == "test_user2"
        assert "logo" in data["user"]
        assert "emoji" in data["user"]
        assert "bot" in data["user"]
        assert "viewer" in data["user"]

        # Should NOT include sensitive data
        assert "api_key" not in data["user"]
        assert "email" not in data["user"]
        assert "webhook_url" not in data["user"]


def test_websocket_get_user_profile_not_found(client, registered_user):
    """Test getting non-existent user profile via WebSocket."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Request non-existent user
        websocket.send_json({"type": "get_user_profile", "username": "nonexistent_user"})

        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "not found" in data["error"].lower()


def test_websocket_get_user_profile_missing_username(client, registered_user):
    """Test getting user profile without username via WebSocket."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Request without username
        websocket.send_json({"type": "get_user_profile"})

        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "username" in data["error"].lower()


def test_websocket_mark_room_read(client, registered_user, registered_user2):
    """Test marking room messages as read via WebSocket."""
    headers2 = {"X-API-Key": registered_user2["api_key"]}

    # User 2 sends room messages
    client.post("/messages", json={"content": "Room message 1"}, headers=headers2)
    client.post("/messages", json={"content": "Room message 2"}, headers=headers2)

    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Check unread messages first
        websocket.send_json({"type": "get_unread_messages"})
        data = websocket.receive_json()
        initial_unread = len(data["messages"])
        assert initial_unread >= 2

        # Mark as read
        websocket.send_json({"type": "mark_room_read"})
        data = websocket.receive_json()
        assert data["status"] == "marked_read"

        # Check unread again - should be 0
        websocket.send_json({"type": "get_unread_messages"})
        data = websocket.receive_json()
        assert len(data["messages"]) == 0


def test_websocket_mark_direct_read(client, registered_user, registered_user2):
    """Test marking direct messages as read via WebSocket."""
    headers2 = {"X-API-Key": registered_user2["api_key"]}

    # User 2 sends DMs to user 1
    client.post(
        "/messages",
        json={"content": "DM 1", "to_username": "test_user"},
        headers=headers2,
    )
    client.post(
        "/messages",
        json={"content": "DM 2", "to_username": "test_user"},
        headers=headers2,
    )

    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Check unread DMs first
        websocket.send_json({"type": "get_unread_direct_messages"})
        data = websocket.receive_json()
        initial_unread = len(data["messages"])
        assert initial_unread >= 2

        # Mark as read
        websocket.send_json({"type": "mark_direct_read", "from_username": "test_user2"})
        data = websocket.receive_json()
        assert data["status"] == "marked_read"

        # Check unread again - should be 0 from user2
        websocket.send_json({"type": "get_unread_direct_messages"})
        data = websocket.receive_json()
        # No messages from user2 should be unread
        user2_unread = [msg for msg in data["messages"] if msg["from_username"] == "test_user2"]
        assert len(user2_unread) == 0


def test_websocket_unknown_message_type(client, registered_user):
    """Test WebSocket with unknown message type."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Send unknown type
        websocket.send_json({"type": "unknown_type", "data": "test"})

        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "Unknown message type" in data["error"]


def test_websocket_message_type_missing(client, registered_user):
    """Test WebSocket message without type field."""
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Send message without type
        websocket.send_json({"content": "Test"})

        # Should still work as a regular room message (backward compatibility)
        data = websocket.receive_json()
        assert data["status"] == "sent"
        assert data["message"]["content"] == "Test"
