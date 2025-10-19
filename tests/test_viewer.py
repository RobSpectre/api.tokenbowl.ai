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


def test_websocket_cannot_send_to_viewer(client, registered_user):
    """Test that WebSocket messages cannot be sent to viewer users."""
    # Register a viewer
    response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    assert response.status_code == 201

    # Try to send a direct message via WebSocket
    with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as websocket:
        # Send direct message to viewer
        websocket.send_json({"content": "Hello viewer", "to_username": "viewer_user"})

        # Should receive error
        data = websocket.receive_json()
        assert "error" in data
        assert "Cannot send messages to viewer user" in data["error"]


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


def test_viewer_receives_websocket_broadcasts(client, registered_user):
    """Test that viewers receive room messages via WebSocket."""
    # Register a viewer
    response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    viewer_api_key = response.json()["api_key"]

    # Connect viewer via WebSocket
    with client.websocket_connect(f"/ws?api_key={viewer_api_key}") as viewer_ws:
        # Regular user sends a room message
        with client.websocket_connect(f"/ws?api_key={registered_user['api_key']}") as user_ws:
            user_ws.send_json({"content": "Room message"})

            # User gets confirmation
            user_data = user_ws.receive_json()
            assert user_data["status"] == "sent"

            # Viewer should receive the broadcast
            viewer_data = viewer_ws.receive_json()
            assert viewer_data["content"] == "Room message"
            assert viewer_data["from_username"] == registered_user["username"]
