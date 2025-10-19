"""Tests for webhook delivery module."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from token_bowl_chat_server.models import Message, MessageType, User
from token_bowl_chat_server.webhook import WebhookDelivery


@pytest_asyncio.fixture
async def webhook_delivery():
    """Create a webhook delivery instance for testing."""
    delivery = WebhookDelivery(timeout=5.0, max_retries=2)
    await delivery.start()
    yield delivery
    await delivery.stop()


@pytest.mark.asyncio
async def test_webhook_delivery_start_stop():
    """Test starting and stopping webhook delivery."""
    delivery = WebhookDelivery()
    assert delivery.client is None

    await delivery.start()
    assert delivery.client is not None

    await delivery.stop()
    assert delivery.client is None


@pytest.mark.asyncio
async def test_deliver_message_success(webhook_delivery):
    """Test successful message delivery."""
    user = User(
        username="test_user",
        api_key="a" * 64,
        webhook_url="https://example.com/webhook",
    )
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    # Mock successful response
    with patch.object(webhook_delivery.client, "post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = await webhook_delivery.deliver_message(user, message)

        assert result is True
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_deliver_message_no_webhook_url(webhook_delivery):
    """Test delivery to user without webhook URL."""
    user = User(username="test_user", api_key="a" * 64)
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    result = await webhook_delivery.deliver_message(user, message)
    assert result is False


@pytest.mark.asyncio
async def test_deliver_message_client_not_initialized():
    """Test delivery when client is not initialized."""
    delivery = WebhookDelivery()
    user = User(
        username="test_user",
        api_key="a" * 64,
        webhook_url="https://example.com/webhook",
    )
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    result = await delivery.deliver_message(user, message)
    assert result is False


@pytest.mark.asyncio
async def test_deliver_message_http_error(webhook_delivery):
    """Test delivery with HTTP error response."""
    user = User(
        username="test_user",
        api_key="a" * 64,
        webhook_url="https://example.com/webhook",
    )
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    # Mock error response
    with patch.object(webhook_delivery.client, "post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        result = await webhook_delivery.deliver_message(user, message)

        assert result is False
        # Should retry (max_retries=2)
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_deliver_message_timeout(webhook_delivery):
    """Test delivery with timeout."""
    user = User(
        username="test_user",
        api_key="a" * 64,
        webhook_url="https://example.com/webhook",
    )
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    # Mock timeout exception
    with patch.object(webhook_delivery.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Timeout")

        result = await webhook_delivery.deliver_message(user, message)

        assert result is False
        # Should retry (max_retries=2)
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_deliver_message_request_error(webhook_delivery):
    """Test delivery with request error."""
    user = User(
        username="test_user",
        api_key="a" * 64,
        webhook_url="https://example.com/webhook",
    )
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    # Mock request error
    with patch.object(webhook_delivery.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.RequestError("Network error")

        result = await webhook_delivery.deliver_message(user, message)

        assert result is False
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_deliver_message_unexpected_error(webhook_delivery):
    """Test delivery with unexpected error."""
    user = User(
        username="test_user",
        api_key="a" * 64,
        webhook_url="https://example.com/webhook",
    )
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    # Mock unexpected error
    with patch.object(webhook_delivery.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = Exception("Unexpected error")

        result = await webhook_delivery.deliver_message(user, message)

        assert result is False
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_deliver_message_retry_success(webhook_delivery):
    """Test delivery succeeds on retry."""
    user = User(
        username="test_user",
        api_key="a" * 64,
        webhook_url="https://example.com/webhook",
    )
    message = Message(
        from_username="sender",
        content="Test message",
        message_type=MessageType.ROOM,
    )

    # Mock first call fails, second succeeds
    with patch.object(webhook_delivery.client, "post", new_callable=AsyncMock) as mock_post:
        mock_response_error = MagicMock()
        mock_response_error.status_code = 500
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_post.side_effect = [mock_response_error, mock_response_success]

        result = await webhook_delivery.deliver_message(user, message)

        assert result is True
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_broadcast_to_webhooks(webhook_delivery):
    """Test broadcasting to multiple webhooks."""
    user1 = User(
        username="user1",
        api_key="a" * 64,
        webhook_url="https://example.com/webhook1",
    )
    user2 = User(
        username="user2",
        api_key="b" * 64,
        webhook_url="https://example.com/webhook2",
    )
    user3 = User(
        username="user3",
        api_key="c" * 64,
    )  # No webhook

    message = Message(
        from_username="sender",
        content="Broadcast message",
        message_type=MessageType.ROOM,
    )

    with patch.object(webhook_delivery.client, "post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        await webhook_delivery.broadcast_to_webhooks(message, [user1, user2, user3])

        # Should call post twice (user1 and user2, not user3)
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_broadcast_to_webhooks_with_exclusion(webhook_delivery):
    """Test broadcasting with username exclusion."""
    user1 = User(
        username="user1",
        api_key="a" * 64,
        webhook_url="https://example.com/webhook1",
    )
    user2 = User(
        username="user2",
        api_key="b" * 64,
        webhook_url="https://example.com/webhook2",
    )

    message = Message(
        from_username="user1",
        content="Broadcast message",
        message_type=MessageType.ROOM,
    )

    with patch.object(webhook_delivery.client, "post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        await webhook_delivery.broadcast_to_webhooks(
            message, [user1, user2], exclude_username="user1"
        )

        # Should only call post once (user2, not user1)
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_broadcast_to_webhooks_no_users(webhook_delivery):
    """Test broadcasting with no eligible users."""
    message = Message(
        from_username="sender",
        content="Broadcast message",
        message_type=MessageType.ROOM,
    )

    # Should not raise any errors
    await webhook_delivery.broadcast_to_webhooks(message, [])
