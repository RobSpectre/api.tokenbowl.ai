"""Tests for storage module."""

from datetime import UTC, datetime, timedelta

import pytest

from token_bowl_chat_server.models import Message, MessageType, User
from token_bowl_chat_server.storage import ChatStorage


def test_add_user():
    """Test adding a user to storage."""
    storage = ChatStorage(db_path=":memory:")
    user = User(username="test", api_key="a" * 32)  # 32 char minimum

    storage.add_user(user)

    assert storage.get_user_by_username("test") == user
    assert storage.get_user_by_api_key("a" * 32) == user


def test_add_duplicate_username():
    """Test that adding duplicate username raises error."""
    storage = ChatStorage(db_path=":memory:")
    user1 = User(username="test", api_key="a" * 32)
    user2 = User(username="test", api_key="b" * 32)

    storage.add_user(user1)

    with pytest.raises(ValueError, match="already exists"):
        storage.add_user(user2)


def test_add_duplicate_api_key():
    """Test that adding duplicate API key raises error."""
    storage = ChatStorage(db_path=":memory:")
    same_key = "c" * 32
    user1 = User(username="user1", api_key=same_key)
    user2 = User(username="user2", api_key=same_key)

    storage.add_user(user1)

    with pytest.raises(ValueError, match="API key already exists"):
        storage.add_user(user2)


def test_get_user_by_username():
    """Test getting user by username."""
    storage = ChatStorage(db_path=":memory:")
    user = User(username="test", api_key="d" * 32)
    storage.add_user(user)

    result = storage.get_user_by_username("test")
    assert result == user

    result = storage.get_user_by_username("nonexistent")
    assert result is None


def test_get_user_by_api_key():
    """Test getting user by API key."""
    storage = ChatStorage(db_path=":memory:")
    secret_key = "e" * 32
    user = User(username="test", api_key=secret_key)
    storage.add_user(user)

    result = storage.get_user_by_api_key(secret_key)
    assert result == user

    result = storage.get_user_by_api_key("f" * 32)
    assert result is None


def test_add_message():
    """Test adding a message."""
    storage = ChatStorage(db_path=":memory:")
    message = Message(
        from_username="user1",
        content="Hello",
        message_type=MessageType.ROOM,
    )

    storage.add_message(message)

    # Verify message was added by retrieving it
    messages = storage.get_recent_messages(limit=10)
    assert len(messages) == 1
    assert messages[0].content == message.content
    assert messages[0].from_username == message.from_username


def test_message_history_limit():
    """Test that message history is limited."""
    storage = ChatStorage(db_path=":memory:", message_history_limit=5)

    # Add more messages than the limit
    for i in range(10):
        message = Message(
            from_username="user",
            content=f"Message {i}",
            message_type=MessageType.ROOM,
        )
        storage.add_message(message)

    # Should only keep the last 5
    messages = storage.get_recent_messages(limit=100)
    assert len(messages) == 5
    assert messages[0].content == "Message 5"
    assert messages[4].content == "Message 9"


def test_get_recent_messages():
    """Test getting recent room messages."""
    storage = ChatStorage(db_path=":memory:")

    # Add room messages
    for i in range(5):
        message = Message(
            from_username="user",
            content=f"Room {i}",
            message_type=MessageType.ROOM,
        )
        storage.add_message(message)

    # Add direct message (should not be included)
    dm = Message(
        from_username="user1",
        to_username="user2",
        content="Direct",
        message_type=MessageType.DIRECT,
    )
    storage.add_message(dm)

    messages = storage.get_recent_messages(limit=10)
    assert len(messages) == 5
    assert all(msg.to_username is None for msg in messages)


def test_get_recent_messages_with_limit():
    """Test getting recent messages with limit and offset."""
    storage = ChatStorage(db_path=":memory:")

    for i in range(10):
        message = Message(
            from_username="user",
            content=f"Message {i}",
            message_type=MessageType.ROOM,
        )
        storage.add_message(message)

    # Get first 3 messages (default offset=0)
    messages = storage.get_recent_messages(limit=3)
    assert len(messages) == 3
    assert messages[0].content == "Message 0"
    assert messages[2].content == "Message 2"

    # Get messages with offset
    messages = storage.get_recent_messages(limit=3, offset=7)
    assert len(messages) == 3
    assert messages[0].content == "Message 7"
    assert messages[2].content == "Message 9"


def test_get_recent_messages_since():
    """Test getting messages since a timestamp."""
    storage = ChatStorage(db_path=":memory:")

    now = datetime.now(UTC)
    past = now - timedelta(hours=1)

    # Add old message
    old_msg = Message(
        from_username="user",
        content="Old",
        message_type=MessageType.ROOM,
    )
    old_msg.timestamp = past
    storage.add_message(old_msg)

    # Add new message
    new_msg = Message(
        from_username="user",
        content="New",
        message_type=MessageType.ROOM,
    )
    storage.add_message(new_msg)

    messages = storage.get_recent_messages(since=now - timedelta(minutes=30))
    assert len(messages) == 1
    assert messages[0].content == "New"


def test_get_direct_messages():
    """Test getting direct messages for a user."""
    storage = ChatStorage(db_path=":memory:")

    # Messages between user1 and user2
    msg1 = Message(
        from_username="user1",
        to_username="user2",
        content="Hello user2",
        message_type=MessageType.DIRECT,
    )
    storage.add_message(msg1)

    msg2 = Message(
        from_username="user2",
        to_username="user1",
        content="Hello user1",
        message_type=MessageType.DIRECT,
    )
    storage.add_message(msg2)

    # Message from user3 to user2
    msg3 = Message(
        from_username="user3",
        to_username="user2",
        content="Hello from user3",
        message_type=MessageType.DIRECT,
    )
    storage.add_message(msg3)

    # Room message (should not be included)
    room_msg = Message(
        from_username="user1",
        content="Room message",
        message_type=MessageType.ROOM,
    )
    storage.add_message(room_msg)

    # Get direct messages for user1
    messages = storage.get_direct_messages("user1")
    assert len(messages) == 2
    assert all(msg.from_username == "user1" or msg.to_username == "user1" for msg in messages)


def test_get_all_users():
    """Test getting all users."""
    storage = ChatStorage(db_path=":memory:")

    user1 = User(username="user1", api_key="g" * 32)
    user2 = User(username="user2", api_key="h" * 32)

    storage.add_user(user1)
    storage.add_user(user2)

    users = storage.get_all_users()
    assert len(users) == 2
    assert user1 in users
    assert user2 in users


def test_delete_user():
    """Test deleting a user."""
    storage = ChatStorage(db_path=":memory:")
    api_key = "i" * 32
    user = User(username="test", api_key=api_key)
    storage.add_user(user)

    result = storage.delete_user("test")
    assert result is True
    assert storage.get_user_by_username("test") is None
    assert storage.get_user_by_api_key(api_key) is None


def test_delete_nonexistent_user():
    """Test deleting a nonexistent user."""
    storage = ChatStorage(db_path=":memory:")

    result = storage.delete_user("nonexistent")
    assert result is False


def test_get_direct_messages_with_since():
    """Test getting direct messages with since parameter."""
    storage = ChatStorage(db_path=":memory:")

    now = datetime.now(UTC)
    past = now - timedelta(hours=1)

    # Add old direct message
    old_msg = Message(
        from_username="user1",
        to_username="user2",
        content="Old DM",
        message_type=MessageType.DIRECT,
    )
    old_msg.timestamp = past
    storage.add_message(old_msg)

    # Add new direct message
    new_msg = Message(
        from_username="user1",
        to_username="user2",
        content="New DM",
        message_type=MessageType.DIRECT,
    )
    storage.add_message(new_msg)

    # Get messages since 30 minutes ago (should only get new one)
    messages = storage.get_direct_messages("user2", since=now - timedelta(minutes=30))
    assert len(messages) == 1
    assert messages[0].content == "New DM"


def test_get_room_messages_count_with_since():
    """Test getting room message count with since parameter."""
    storage = ChatStorage(db_path=":memory:")

    now = datetime.now(UTC)
    past = now - timedelta(hours=1)

    # Add old message
    old_msg = Message(
        from_username="user",
        content="Old",
        message_type=MessageType.ROOM,
    )
    old_msg.timestamp = past
    storage.add_message(old_msg)

    # Add new messages
    for i in range(3):
        msg = Message(
            from_username="user",
            content=f"New {i}",
            message_type=MessageType.ROOM,
        )
        storage.add_message(msg)

    # Count messages since 30 minutes ago
    count = storage.get_room_messages_count(since=now - timedelta(minutes=30))
    assert count == 3


def test_get_direct_messages_count_with_since():
    """Test getting direct message count with since parameter."""
    storage = ChatStorage(db_path=":memory:")

    now = datetime.now(UTC)
    past = now - timedelta(hours=1)

    # Add old direct message
    old_msg = Message(
        from_username="user1",
        to_username="user2",
        content="Old DM",
        message_type=MessageType.DIRECT,
    )
    old_msg.timestamp = past
    storage.add_message(old_msg)

    # Add new direct messages
    for i in range(2):
        msg = Message(
            from_username="user1",
            to_username="user2",
            content=f"New DM {i}",
            message_type=MessageType.DIRECT,
        )
        storage.add_message(msg)

    # Count messages since 30 minutes ago
    count = storage.get_direct_messages_count("user2", since=now - timedelta(minutes=30))
    assert count == 2
