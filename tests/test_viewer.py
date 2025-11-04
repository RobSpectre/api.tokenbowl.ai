"""Tests for viewer functionality."""


def test_register_viewer(client):
    """Test registering a viewer user."""
    response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "viewer_user"
    assert data["viewer"] is True
    assert "api_key" in data


def test_register_non_viewer(client):
    """Test registering a non-viewer user (default)."""
    response = client.post(
        "/register",
        json={"username": "normal_user"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "normal_user"
    assert data["viewer"] is False


def test_viewers_not_in_users_list(client, registered_user):
    """Test that viewers are not included in the users list."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # Register a viewer
    response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    viewer_data = response.json()
    assert viewer_data["viewer"] is True

    # Get users list
    response = client.get("/users", headers=headers)
    assert response.status_code == 200
    users = response.json()
    usernames = [user["username"] for user in users]

    # Viewer should not be in the list
    assert "viewer_user" not in usernames
    # Regular user should be in the list
    assert registered_user["username"] in usernames


def test_cannot_send_direct_message_to_viewer(client, registered_user):
    """Test that direct messages cannot be sent to viewer users."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # Register a viewer
    response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    assert response.status_code == 201

    # Try to send a direct message to the viewer
    response = client.post(
        "/messages",
        json={"content": "Hello viewer!", "to_username": "viewer_user"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Cannot send messages to viewer user" in response.json()["detail"]


def test_viewer_can_view_messages(client, registered_user):
    """Test that viewers can view all messages."""
    # Register a viewer
    response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    viewer_api_key = response.json()["api_key"]
    viewer_headers = {"X-API-Key": viewer_api_key}

    # Regular user sends a message
    headers = {"X-API-Key": registered_user["api_key"]}
    client.post(
        "/messages",
        json={"content": "Test message"},
        headers=headers,
    )

    # Viewer should be able to get messages
    response = client.get("/messages", headers=viewer_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) > 0
    assert any(msg["content"] == "Test message" for msg in data["messages"])


def test_viewer_cannot_send_messages(client):
    """Test that viewers cannot send messages (read-only access)."""
    # Register a viewer
    response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    viewer_api_key = response.json()["api_key"]
    viewer_headers = {"X-API-Key": viewer_api_key}

    # Viewer attempts to send a message (should be forbidden)
    response = client.post(
        "/messages",
        json={"content": "Viewer observation"},
        headers=viewer_headers,
    )
    assert response.status_code == 403
    assert "does not have permission to send room messages" in response.json()["detail"]


def test_multiple_viewers_not_in_users_list(client, registered_user):
    """Test that multiple viewers are all excluded from users list."""
    headers = {"X-API-Key": registered_user["api_key"]}

    # Register multiple viewers
    for i in range(3):
        client.post(
            "/register",
            json={"username": f"viewer_{i}", "viewer": True},
        )

    # Register another regular user
    client.post(
        "/register",
        json={"username": "regular_user"},
    )

    # Get users list
    response = client.get("/users", headers=headers)
    assert response.status_code == 200
    users = response.json()
    usernames = [user["username"] for user in users]

    # No viewers should be in the list
    assert "viewer_0" not in usernames
    assert "viewer_1" not in usernames
    assert "viewer_2" not in usernames

    # Regular users should be in the list
    assert registered_user["username"] in usernames
    assert "regular_user" in usernames


def test_viewer_with_logo(client):
    """Test that viewers can have logos."""
    response = client.post(
        "/register",
        json={"username": "viewer_with_logo", "viewer": True, "logo": "claude-color.png"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["viewer"] is True
    assert data["logo"] == "claude-color.png"


def test_viewer_can_see_all_direct_messages(client, registered_user, registered_user2):
    """Test that viewers can see ALL direct messages between users."""
    # Register a viewer
    response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    viewer_api_key = response.json()["api_key"]
    viewer_headers = {"X-API-Key": viewer_api_key}

    # User 1 sends a direct message to User 2
    headers1 = {"X-API-Key": registered_user["api_key"]}
    response = client.post(
        "/messages",
        json={"content": "Secret message to user2", "to_username": registered_user2["username"]},
        headers=headers1,
    )
    assert response.status_code == 201

    # User 2 sends a direct message to User 1
    headers2 = {"X-API-Key": registered_user2["api_key"]}
    response = client.post(
        "/messages",
        json={"content": "Reply from user2", "to_username": registered_user["username"]},
        headers=headers2,
    )
    assert response.status_code == 201

    # Viewer should be able to see ALL direct messages
    response = client.get("/messages/direct", headers=viewer_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] == 2  # Should see both DMs

    messages = data["messages"]
    assert len(messages) == 2

    # Verify viewer can see both messages
    contents = [msg["content"] for msg in messages]
    assert "Secret message to user2" in contents
    assert "Reply from user2" in contents

    # Regular user 1 should only see their own DMs (both messages involve them)
    response = client.get("/messages/direct", headers=headers1)
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] == 2  # Both messages involve user1

    # Create a third user and have them exchange messages with user2
    response = client.post(
        "/register",
        json={"username": "user3"},
    )
    user3_api_key = response.json()["api_key"]
    headers3 = {"X-API-Key": user3_api_key}

    # User 3 sends DM to User 2
    response = client.post(
        "/messages",
        json={"content": "Message from user3", "to_username": registered_user2["username"]},
        headers=headers3,
    )
    assert response.status_code == 201

    # Viewer should now see 3 total DMs
    response = client.get("/messages/direct", headers=viewer_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] == 3

    # User 1 should still only see their 2 DMs (doesn't see user3-user2 conversation)
    response = client.get("/messages/direct", headers=headers1)
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] == 2
