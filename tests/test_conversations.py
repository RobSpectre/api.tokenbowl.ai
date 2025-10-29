"""Tests for conversation functionality."""

import pytest


@pytest.fixture
def registered_viewer(client):
    """Register a viewer user."""
    response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    assert response.status_code == 201
    return response.json()


def test_create_conversation_rest(client, registered_user):
    """Test creating a conversation via REST API."""
    # First, create some messages
    api_key = registered_user["api_key"]

    # Send a room message
    response = client.post(
        "/messages",
        json={"content": "Test message 1"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    message1_id = response.json()["id"]

    # Send another room message
    response = client.post(
        "/messages",
        json={"content": "Test message 2"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    message2_id = response.json()["id"]

    # Create a conversation
    response = client.post(
        "/conversations",
        json={
            "title": "Test Conversation",
            "message_ids": [message1_id, message2_id],
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Conversation"
    assert len(data["message_ids"]) == 2
    assert message1_id in data["message_ids"]
    assert message2_id in data["message_ids"]
    assert data["created_by_username"] == registered_user["username"]


def test_create_conversation_without_title_rest(client, registered_user):
    """Test creating a conversation without a title via REST API."""
    api_key = registered_user["api_key"]

    # Send a room message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    # Create a conversation without a title
    response = client.post(
        "/conversations",
        json={"message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] is None
    assert len(data["message_ids"]) == 1


def test_create_conversation_with_invalid_message_id_rest(client, registered_user):
    """Test creating a conversation with invalid message ID via REST API."""
    api_key = registered_user["api_key"]

    # Try to create a conversation with a non-existent message ID
    response = client.post(
        "/conversations",
        json={
            "title": "Test Conversation",
            "message_ids": ["00000000-0000-0000-0000-000000000000"],
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_get_conversations_rest(client, registered_user):
    """Test getting all conversations via REST API."""
    api_key = registered_user["api_key"]

    # Send a room message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    # Create two conversations
    client.post(
        "/conversations",
        json={"title": "Conversation 1", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )
    client.post(
        "/conversations",
        json={"title": "Conversation 2", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )

    # Get all conversations
    response = client.get(
        "/conversations",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["conversations"]) == 2
    assert data["pagination"]["total"] == 2


def test_get_conversation_rest(client, registered_user):
    """Test getting a specific conversation via REST API."""
    api_key = registered_user["api_key"]

    # Send a room message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    # Create a conversation
    response = client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )
    conversation_id = response.json()["id"]

    # Get the conversation
    response = client.get(
        f"/conversations/{conversation_id}",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == conversation_id
    assert data["title"] == "Test Conversation"


def test_get_conversation_unauthorized_rest(client, registered_user, registered_user2):
    """Test that users can't view other users' conversations via REST API."""
    api_key1 = registered_user["api_key"]
    api_key2 = registered_user2["api_key"]

    # User 1 sends a message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key1},
    )
    message_id = response.json()["id"]

    # User 1 creates a conversation
    response = client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key1},
    )
    conversation_id = response.json()["id"]

    # User 2 tries to get the conversation
    response = client.get(
        f"/conversations/{conversation_id}",
        headers={"X-API-Key": api_key2},
    )
    assert response.status_code == 403


def test_update_conversation_rest(client, registered_user):
    """Test updating a conversation via REST API."""
    api_key = registered_user["api_key"]

    # Send two messages
    response = client.post(
        "/messages",
        json={"content": "Test message 1"},
        headers={"X-API-Key": api_key},
    )
    message1_id = response.json()["id"]

    response = client.post(
        "/messages",
        json={"content": "Test message 2"},
        headers={"X-API-Key": api_key},
    )
    message2_id = response.json()["id"]

    # Create a conversation
    response = client.post(
        "/conversations",
        json={"title": "Original Title", "message_ids": [message1_id]},
        headers={"X-API-Key": api_key},
    )
    conversation_id = response.json()["id"]

    # Update the conversation
    response = client.patch(
        f"/conversations/{conversation_id}",
        json={"title": "Updated Title", "message_ids": [message1_id, message2_id]},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert len(data["message_ids"]) == 2


def test_update_conversation_title_only_rest(client, registered_user):
    """Test updating only the title of a conversation via REST API."""
    api_key = registered_user["api_key"]

    # Send a message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    message_id = response.json()["id"]

    # Create a conversation
    response = client.post(
        "/conversations",
        json={"title": "Original Title", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )
    conversation_id = response.json()["id"]

    # Update only the title
    response = client.patch(
        f"/conversations/{conversation_id}",
        json={"title": "New Title"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"
    assert len(data["message_ids"]) == 1


def test_update_conversation_unauthorized_rest(client, registered_user, registered_user2):
    """Test that users can't update other users' conversations via REST API."""
    api_key1 = registered_user["api_key"]
    api_key2 = registered_user2["api_key"]

    # User 1 sends a message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key1},
    )
    message_id = response.json()["id"]

    # User 1 creates a conversation
    response = client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key1},
    )
    conversation_id = response.json()["id"]

    # User 2 tries to update the conversation
    response = client.patch(
        f"/conversations/{conversation_id}",
        json={"title": "Hacked Title"},
        headers={"X-API-Key": api_key2},
    )
    assert response.status_code == 403


def test_delete_conversation_rest(client, registered_user):
    """Test deleting a conversation via REST API."""
    api_key = registered_user["api_key"]

    # Send a message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    message_id = response.json()["id"]

    # Create a conversation
    response = client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )
    conversation_id = response.json()["id"]

    # Delete the conversation
    response = client.delete(
        f"/conversations/{conversation_id}",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 204

    # Verify it's deleted
    response = client.get(
        f"/conversations/{conversation_id}",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 404


def test_delete_conversation_unauthorized_rest(client, registered_user, registered_user2):
    """Test that users can't delete other users' conversations via REST API."""
    api_key1 = registered_user["api_key"]
    api_key2 = registered_user2["api_key"]

    # User 1 sends a message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key1},
    )
    message_id = response.json()["id"]

    # User 1 creates a conversation
    response = client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key1},
    )
    conversation_id = response.json()["id"]

    # User 2 tries to delete the conversation
    response = client.delete(
        f"/conversations/{conversation_id}",
        headers={"X-API-Key": api_key2},
    )
    assert response.status_code == 403


def test_create_conversation_websocket(client, registered_user):
    """Test creating a conversation via WebSocket."""
    api_key = registered_user["api_key"]

    # Send a message via REST to get a message ID
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    message_id = response.json()["id"]

    # Connect to WebSocket and create conversation
    with client.websocket_connect(f"/ws?api_key={api_key}") as websocket:
        # Create conversation
        websocket.send_json(
            {
                "type": "create_conversation",
                "title": "WebSocket Conversation",
                "message_ids": [message_id],
            }
        )

        # Receive response
        response = websocket.receive_json()
        assert response["type"] == "conversation_created"
        assert response["conversation"]["title"] == "WebSocket Conversation"
        assert len(response["conversation"]["message_ids"]) == 1


def test_get_conversations_websocket(client, registered_user):
    """Test getting conversations via WebSocket."""
    api_key = registered_user["api_key"]

    # Send a message and create a conversation via REST
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    message_id = response.json()["id"]

    client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )

    # Connect to WebSocket and get conversations
    with client.websocket_connect(f"/ws?api_key={api_key}") as websocket:
        # Get conversations
        websocket.send_json(
            {
                "type": "get_conversations",
                "limit": 50,
                "offset": 0,
            }
        )

        # Receive response
        response = websocket.receive_json()
        assert response["type"] == "conversations"
        assert len(response["conversations"]) == 1
        assert response["pagination"]["total"] == 1


def test_get_conversation_websocket(client, registered_user):
    """Test getting a specific conversation via WebSocket."""
    api_key = registered_user["api_key"]

    # Send a message and create a conversation via REST
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    message_id = response.json()["id"]

    response = client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )
    conversation_id = response.json()["id"]

    # Connect to WebSocket and get the conversation
    with client.websocket_connect(f"/ws?api_key={api_key}") as websocket:
        # Get conversation
        websocket.send_json(
            {
                "type": "get_conversation",
                "conversation_id": conversation_id,
            }
        )

        # Receive response
        response = websocket.receive_json()
        assert response["type"] == "conversation"
        assert response["conversation"]["id"] == conversation_id
        assert response["conversation"]["title"] == "Test Conversation"


def test_update_conversation_websocket(client, registered_user):
    """Test updating a conversation via WebSocket."""
    api_key = registered_user["api_key"]

    # Send messages and create a conversation via REST
    response = client.post(
        "/messages",
        json={"content": "Test message 1"},
        headers={"X-API-Key": api_key},
    )
    message1_id = response.json()["id"]

    response = client.post(
        "/messages",
        json={"content": "Test message 2"},
        headers={"X-API-Key": api_key},
    )
    message2_id = response.json()["id"]

    response = client.post(
        "/conversations",
        json={"title": "Original Title", "message_ids": [message1_id]},
        headers={"X-API-Key": api_key},
    )
    conversation_id = response.json()["id"]

    # Connect to WebSocket and update the conversation
    with client.websocket_connect(f"/ws?api_key={api_key}") as websocket:
        # Update conversation
        websocket.send_json(
            {
                "type": "update_conversation",
                "conversation_id": conversation_id,
                "title": "Updated via WebSocket",
                "message_ids": [message1_id, message2_id],
            }
        )

        # Receive response
        response = websocket.receive_json()
        assert response["type"] == "conversation_updated"
        assert response["conversation"]["title"] == "Updated via WebSocket"
        assert len(response["conversation"]["message_ids"]) == 2


def test_delete_conversation_websocket(client, registered_user):
    """Test deleting a conversation via WebSocket."""
    api_key = registered_user["api_key"]

    # Send a message and create a conversation via REST
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    message_id = response.json()["id"]

    response = client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )
    conversation_id = response.json()["id"]

    # Connect to WebSocket and delete the conversation
    with client.websocket_connect(f"/ws?api_key={api_key}") as websocket:
        # Delete conversation
        websocket.send_json(
            {
                "type": "delete_conversation",
                "conversation_id": conversation_id,
            }
        )

        # Receive response
        response = websocket.receive_json()
        assert response["type"] == "conversation_deleted"
        assert response["conversation_id"] == conversation_id


def test_viewer_can_see_all_conversations_rest(
    client, registered_user, registered_user2, registered_viewer
):
    """Test that viewers can see all conversations via REST API."""
    api_key1 = registered_user["api_key"]
    api_key2 = registered_user2["api_key"]
    viewer_api_key = registered_viewer["api_key"]

    # User 1 sends a message and creates a conversation
    response = client.post(
        "/messages",
        json={"content": "User 1 message"},
        headers={"X-API-Key": api_key1},
    )
    message1_id = response.json()["id"]

    client.post(
        "/conversations",
        json={"title": "User 1 Conversation", "message_ids": [message1_id]},
        headers={"X-API-Key": api_key1},
    )

    # User 2 sends a message and creates a conversation
    response = client.post(
        "/messages",
        json={"content": "User 2 message"},
        headers={"X-API-Key": api_key2},
    )
    message2_id = response.json()["id"]

    client.post(
        "/conversations",
        json={"title": "User 2 Conversation", "message_ids": [message2_id]},
        headers={"X-API-Key": api_key2},
    )

    # Viewer should see all conversations
    response = client.get(
        "/conversations",
        headers={"X-API-Key": viewer_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["conversations"]) == 2
    assert data["pagination"]["total"] == 2

    # Regular user should only see their own
    response = client.get(
        "/conversations",
        headers={"X-API-Key": api_key1},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["conversations"]) == 1
    assert data["conversations"][0]["created_by_username"] == registered_user["username"]


def test_viewer_can_see_specific_conversation_rest(client, registered_user, registered_viewer):
    """Test that viewers can view any specific conversation via REST API."""
    user_api_key = registered_user["api_key"]
    viewer_api_key = registered_viewer["api_key"]

    # User creates a conversation
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": user_api_key},
    )
    message_id = response.json()["id"]

    response = client.post(
        "/conversations",
        json={"title": "User Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": user_api_key},
    )
    conversation_id = response.json()["id"]

    # Viewer should be able to view it
    response = client.get(
        f"/conversations/{conversation_id}",
        headers={"X-API-Key": viewer_api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == conversation_id
    assert data["title"] == "User Conversation"


def test_viewer_can_see_all_conversations_websocket(
    client, registered_user, registered_user2, registered_viewer
):
    """Test that viewers can see all conversations via WebSocket."""
    api_key1 = registered_user["api_key"]
    api_key2 = registered_user2["api_key"]
    viewer_api_key = registered_viewer["api_key"]

    # User 1 sends a message and creates a conversation
    response = client.post(
        "/messages",
        json={"content": "User 1 message"},
        headers={"X-API-Key": api_key1},
    )
    message1_id = response.json()["id"]

    client.post(
        "/conversations",
        json={"title": "User 1 Conversation", "message_ids": [message1_id]},
        headers={"X-API-Key": api_key1},
    )

    # User 2 sends a message and creates a conversation
    response = client.post(
        "/messages",
        json={"content": "User 2 message"},
        headers={"X-API-Key": api_key2},
    )
    message2_id = response.json()["id"]

    client.post(
        "/conversations",
        json={"title": "User 2 Conversation", "message_ids": [message2_id]},
        headers={"X-API-Key": api_key2},
    )

    # Connect as viewer and get conversations
    with client.websocket_connect(f"/ws?api_key={viewer_api_key}") as websocket:
        websocket.send_json(
            {
                "type": "get_conversations",
                "limit": 50,
                "offset": 0,
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "conversations"
        assert len(response["conversations"]) == 2
        assert response["pagination"]["total"] == 2


def test_viewer_can_see_specific_conversation_websocket(client, registered_user, registered_viewer):
    """Test that viewers can view any specific conversation via WebSocket."""
    user_api_key = registered_user["api_key"]
    viewer_api_key = registered_viewer["api_key"]

    # User creates a conversation
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": user_api_key},
    )
    message_id = response.json()["id"]

    response = client.post(
        "/conversations",
        json={"title": "User Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": user_api_key},
    )
    conversation_id = response.json()["id"]

    # Connect as viewer and get the conversation
    with client.websocket_connect(f"/ws?api_key={viewer_api_key}") as websocket:
        websocket.send_json(
            {
                "type": "get_conversation",
                "conversation_id": conversation_id,
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "conversation"
        assert response["conversation"]["id"] == conversation_id
        assert response["conversation"]["title"] == "User Conversation"


def test_admin_can_delete_any_conversation_rest(client, registered_user, registered_admin):
    """Test that admins can delete any conversation via REST API."""
    user_api_key = registered_user["api_key"]
    admin_api_key = registered_admin["api_key"]

    # User creates a conversation
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": user_api_key},
    )
    message_id = response.json()["id"]

    response = client.post(
        "/conversations",
        json={"title": "User Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": user_api_key},
    )
    conversation_id = response.json()["id"]

    # Admin should be able to delete it using admin endpoint
    response = client.delete(
        f"/admin/conversations/{conversation_id}",
        headers={"X-API-Key": admin_api_key},
    )
    assert response.status_code == 204

    # Verify it's deleted
    response = client.get(
        f"/conversations/{conversation_id}",
        headers={"X-API-Key": user_api_key},
    )
    assert response.status_code == 404


def test_admin_delete_nonexistent_conversation_rest(client, registered_admin):
    """Test that admins get 404 when deleting nonexistent conversation via REST API."""
    admin_api_key = registered_admin["api_key"]

    # Try to delete a non-existent conversation
    response = client.delete(
        "/admin/conversations/00000000-0000-0000-0000-000000000000",
        headers={"X-API-Key": admin_api_key},
    )
    assert response.status_code == 404


def test_non_admin_cannot_use_admin_delete_endpoint_rest(client, registered_user, registered_user2):
    """Test that non-admins cannot use the admin delete endpoint via REST API."""
    user1_api_key = registered_user["api_key"]
    user2_api_key = registered_user2["api_key"]

    # User 1 creates a conversation
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": user1_api_key},
    )
    message_id = response.json()["id"]

    response = client.post(
        "/conversations",
        json={"title": "User 1 Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": user1_api_key},
    )
    conversation_id = response.json()["id"]

    # User 2 (non-admin) tries to delete it using admin endpoint
    response = client.delete(
        f"/admin/conversations/{conversation_id}",
        headers={"X-API-Key": user2_api_key},
    )
    assert response.status_code == 403


def test_admin_can_delete_any_conversation_websocket(client, registered_user, registered_admin):
    """Test that admins can delete any conversation via WebSocket."""
    user_api_key = registered_user["api_key"]
    admin_api_key = registered_admin["api_key"]

    # User creates a conversation
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": user_api_key},
    )
    message_id = response.json()["id"]

    response = client.post(
        "/conversations",
        json={"title": "User Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": user_api_key},
    )
    conversation_id = response.json()["id"]

    # Connect as admin and delete the conversation
    with client.websocket_connect(f"/ws?api_key={admin_api_key}") as websocket:
        websocket.send_json(
            {
                "type": "delete_conversation",
                "conversation_id": conversation_id,
            }
        )

        response = websocket.receive_json()
        assert response["type"] == "conversation_deleted"
        assert response["conversation_id"] == conversation_id

    # Verify it's deleted
    response = client.get(
        f"/conversations/{conversation_id}",
        headers={"X-API-Key": user_api_key},
    )
    assert response.status_code == 404


def test_create_conversation_with_description_rest(client, registered_user):
    """Test creating a conversation with a description via REST API."""
    api_key = registered_user["api_key"]

    # Send a room message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    # Create a conversation with description
    response = client.post(
        "/conversations",
        json={
            "title": "Test Conversation",
            "description": "This is a detailed description of what this conversation is about.",
            "message_ids": [message_id],
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Conversation"
    assert (
        data["description"] == "This is a detailed description of what this conversation is about."
    )
    assert len(data["message_ids"]) == 1


def test_create_conversation_without_description_rest(client, registered_user):
    """Test creating a conversation without a description via REST API."""
    api_key = registered_user["api_key"]

    # Send a room message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    # Create a conversation without description
    response = client.post(
        "/conversations",
        json={
            "title": "Test Conversation",
            "message_ids": [message_id],
        },
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Conversation"
    assert data["description"] is None


def test_update_conversation_description_rest(client, registered_user):
    """Test updating a conversation's description via REST API."""
    api_key = registered_user["api_key"]

    # Send a message
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    message_id = response.json()["id"]

    # Create a conversation without description
    response = client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )
    conversation_id = response.json()["id"]

    # Update to add description
    response = client.patch(
        f"/conversations/{conversation_id}",
        json={"description": "This conversation now has a description."},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "This conversation now has a description."
    assert data["title"] == "Test Conversation"

    # Update description to a new value
    response = client.patch(
        f"/conversations/{conversation_id}",
        json={"description": "Updated description text."},
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "Updated description text."


def test_create_conversation_with_description_websocket(client, registered_user):
    """Test creating a conversation with a description via WebSocket."""
    api_key = registered_user["api_key"]

    # Send a message via REST to get a message ID
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    message_id = response.json()["id"]

    # Connect to WebSocket and create conversation with description
    with client.websocket_connect(f"/ws?api_key={api_key}") as websocket:
        # Create conversation
        websocket.send_json(
            {
                "type": "create_conversation",
                "title": "WebSocket Conversation",
                "description": "This conversation was created via WebSocket with a description.",
                "message_ids": [message_id],
            }
        )

        # Receive response
        response = websocket.receive_json()
        assert response["type"] == "conversation_created"
        assert response["conversation"]["title"] == "WebSocket Conversation"
        assert (
            response["conversation"]["description"]
            == "This conversation was created via WebSocket with a description."
        )
        assert len(response["conversation"]["message_ids"]) == 1


def test_update_conversation_description_websocket(client, registered_user):
    """Test updating a conversation's description via WebSocket."""
    api_key = registered_user["api_key"]

    # Send a message and create a conversation via REST
    response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers={"X-API-Key": api_key},
    )
    message_id = response.json()["id"]

    response = client.post(
        "/conversations",
        json={"title": "Test Conversation", "message_ids": [message_id]},
        headers={"X-API-Key": api_key},
    )
    conversation_id = response.json()["id"]

    # Connect to WebSocket and update the conversation
    with client.websocket_connect(f"/ws?api_key={api_key}") as websocket:
        # Update conversation with description
        websocket.send_json(
            {
                "type": "update_conversation",
                "conversation_id": conversation_id,
                "description": "Description added via WebSocket.",
            }
        )

        # Receive response
        response = websocket.receive_json()
        assert response["type"] == "conversation_updated"
        assert response["conversation"]["description"] == "Description added via WebSocket."
        assert response["conversation"]["title"] == "Test Conversation"
