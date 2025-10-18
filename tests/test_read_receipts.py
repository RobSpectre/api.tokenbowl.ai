"""Tests for read receipts functionality."""

import pytest
from fastapi.testclient import TestClient

from token_bowl_chat_server.server import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


def test_get_unread_count_no_messages(client, registered_user):
    """Test getting unread count when there are no messages."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/messages/unread/count", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["unread_room_messages"] == 0
    assert data["unread_direct_messages"] == 0
    assert data["total_unread"] == 0


def test_get_unread_room_messages(client, registered_user, registered_user2):
    """Test getting unread room messages."""
    # User 2 sends a room message
    headers2 = {"X-API-Key": registered_user2["api_key"]}
    client.post(
        "/messages",
        json={"content": "Hello room!"},
        headers=headers2,
    )

    # User 1 should see it as unread
    headers1 = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/messages/unread", headers=headers1)
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 1
    assert messages[0]["content"] == "Hello room!"
    assert messages[0]["from_username"] == registered_user2["username"]


def test_get_unread_direct_messages(client, registered_user, registered_user2):
    """Test getting unread direct messages."""
    # User 2 sends a direct message to user 1
    headers2 = {"X-API-Key": registered_user2["api_key"]}
    client.post(
        "/messages",
        json={"content": "Hello direct!", "to_username": registered_user["username"]},
        headers=headers2,
    )

    # User 1 should see it as unread
    headers1 = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/messages/direct/unread", headers=headers1)
    assert response.status_code == 200
    messages = response.json()
    assert len(messages) == 1
    assert messages[0]["content"] == "Hello direct!"
    assert messages[0]["from_username"] == registered_user2["username"]


def test_mark_message_as_read(client, registered_user, registered_user2):
    """Test marking a message as read."""
    # User 2 sends a message
    headers2 = {"X-API-Key": registered_user2["api_key"]}
    msg_response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers=headers2,
    )
    message_id = msg_response.json()["id"]

    # User 1 sees it as unread
    headers1 = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/messages/unread", headers=headers1)
    assert len(response.json()) == 1

    # User 1 marks it as read
    response = client.post(f"/messages/{message_id}/read", headers=headers1)
    assert response.status_code == 204

    # Now user 1 should have no unread messages
    response = client.get("/messages/unread", headers=headers1)
    assert len(response.json()) == 0


def test_mark_message_as_read_twice(client, registered_user, registered_user2):
    """Test marking a message as read twice doesn't cause errors."""
    # User 2 sends a message
    headers2 = {"X-API-Key": registered_user2["api_key"]}
    msg_response = client.post(
        "/messages",
        json={"content": "Test message"},
        headers=headers2,
    )
    message_id = msg_response.json()["id"]

    headers1 = {"X-API-Key": registered_user["api_key"]}

    # Mark as read twice
    response1 = client.post(f"/messages/{message_id}/read", headers=headers1)
    assert response1.status_code == 204

    response2 = client.post(f"/messages/{message_id}/read", headers=headers1)
    assert response2.status_code == 204


def test_mark_nonexistent_message_as_read(client, registered_user):
    """Test marking a nonexistent message as read."""
    headers = {"X-API-Key": registered_user["api_key"]}
    response = client.post("/messages/nonexistent-id/read", headers=headers)
    assert response.status_code == 404


def test_mark_all_messages_as_read(client, registered_user, registered_user2):
    """Test marking all messages as read."""
    # User 2 sends multiple messages
    headers2 = {"X-API-Key": registered_user2["api_key"]}
    for i in range(5):
        client.post(
            "/messages",
            json={"content": f"Message {i}"},
            headers=headers2,
        )

    # User 1 should have 5 unread messages
    headers1 = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/messages/unread", headers=headers1)
    assert len(response.json()) == 5

    # Mark all as read
    response = client.post("/messages/mark-all-read", headers=headers1)
    assert response.status_code == 200
    data = response.json()
    assert data["marked_as_read"] == 5

    # Now user 1 should have no unread messages
    response = client.get("/messages/unread", headers=headers1)
    assert len(response.json()) == 0


def test_unread_count_after_reading_messages(client, registered_user, registered_user2):
    """Test unread count decreases after reading messages."""
    # User 2 sends room and direct messages
    headers2 = {"X-API-Key": registered_user2["api_key"]}
    client.post("/messages", json={"content": "Room 1"}, headers=headers2)
    client.post("/messages", json={"content": "Room 2"}, headers=headers2)
    msg_response = client.post(
        "/messages",
        json={"content": "Direct", "to_username": registered_user["username"]},
        headers=headers2,
    )
    direct_message_id = msg_response.json()["id"]

    # Check initial unread count
    headers1 = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/messages/unread/count", headers=headers1)
    data = response.json()
    assert data["unread_room_messages"] == 2
    assert data["unread_direct_messages"] == 1
    assert data["total_unread"] == 3

    # Mark direct message as read
    client.post(f"/messages/{direct_message_id}/read", headers=headers1)

    # Check updated count
    response = client.get("/messages/unread/count", headers=headers1)
    data = response.json()
    assert data["unread_room_messages"] == 2
    assert data["unread_direct_messages"] == 0
    assert data["total_unread"] == 2


def test_sender_doesnt_see_own_message_as_unread(client, registered_user):
    """Test that senders don't see their own messages as unread."""
    headers = {"X-API-Key": registered_user["api_key"]}
    client.post("/messages", json={"content": "My message"}, headers=headers)

    # Sender should not see their own message as unread
    response = client.get("/messages/unread", headers=headers)
    assert len(response.json()) == 0


def test_unread_messages_pagination(client, registered_user, registered_user2):
    """Test pagination for unread messages."""
    # User 2 sends 10 messages
    headers2 = {"X-API-Key": registered_user2["api_key"]}
    for i in range(10):
        client.post(
            "/messages",
            json={"content": f"Message {i}"},
            headers=headers2,
        )

    # Get first 5 unread messages
    headers1 = {"X-API-Key": registered_user["api_key"]}
    response = client.get("/messages/unread?limit=5&offset=0", headers=headers1)
    messages = response.json()
    assert len(messages) == 5

    # Get next 5 unread messages
    response = client.get("/messages/unread?limit=5&offset=5", headers=headers1)
    messages = response.json()
    assert len(messages) == 5


def test_unread_direct_messages_only_for_recipient(client, registered_user, registered_user2):
    """Test that only the recipient sees direct messages as unread."""
    # User 1 sends a direct message to user 2
    headers1 = {"X-API-Key": registered_user["api_key"]}
    client.post(
        "/messages",
        json={"content": "DM to user2", "to_username": registered_user2["username"]},
        headers=headers1,
    )

    # User 1 (sender) should not see it as unread
    response = client.get("/messages/direct/unread", headers=headers1)
    assert len(response.json()) == 0

    # User 2 (recipient) should see it as unread
    headers2 = {"X-API-Key": registered_user2["api_key"]}
    response = client.get("/messages/direct/unread", headers=headers2)
    messages = response.json()
    assert len(messages) == 1
    assert messages[0]["content"] == "DM to user2"
