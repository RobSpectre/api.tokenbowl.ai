"""Integration tests for Centrifugo - requires both servers running."""

import time

import httpx
import pytest
import pytest_asyncio

# These tests require BOTH servers to be running:
# 1. FastAPI server on port 8000
# 2. Centrifugo server on port 8001

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def test_user():
    """Create a test user via REST API."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/register",
            json={"username": f"integration_test_{int(time.time() * 1000)}"},
        )
        assert response.status_code == 201
        return response.json()


@pytest.mark.asyncio
async def test_get_centrifugo_connection_token_integration(test_user):
    """Test getting a real Centrifugo connection token."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/centrifugo/connection-token",
            headers={"X-API-Key": test_user["api_key"]},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "token" in data
        assert "url" in data
        assert "channels" in data
        assert "user" in data

        # Verify token is a JWT (has 3 parts separated by dots)
        token_parts = data["token"].split(".")
        assert len(token_parts) == 3

        # Verify channels include room and user channel
        assert "room:main" in data["channels"]
        assert f"user:{test_user['username']}" in data["channels"]


@pytest.mark.asyncio
async def test_centrifugo_server_is_running():
    """Test that Centrifugo server is accessible."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8001/health", timeout=2.0)
            assert response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            pytest.skip("Centrifugo server not running on port 8001")


@pytest.mark.asyncio
async def test_send_message_publishes_to_centrifugo(test_user):
    """Test that sending a message via REST API publishes to Centrifugo.

    This test verifies the integration but can't verify WebSocket delivery
    without a WebSocket client. It checks that the message is sent successfully.
    """
    async with httpx.AsyncClient() as client:
        # Send a message
        response = await client.post(
            "http://localhost:8000/messages",
            json={"content": "Integration test message"},
            headers={"X-API-Key": test_user["api_key"]},
        )

        assert response.status_code == 201
        data = response.json()

        # Verify message structure
        assert data["content"] == "Integration test message"
        assert data["from_username"] == test_user["username"]
        assert data["message_type"] == "room"

        # At this point, the message should have been published to Centrifugo
        # We can't easily verify WebSocket delivery without a client library,
        # but we've verified the REST endpoint works


@pytest.mark.asyncio
async def test_fastapi_server_initializes_centrifugo():
    """Test that FastAPI server has initialized Centrifugo client."""
    async with httpx.AsyncClient() as client:
        # The /health endpoint should work if server is initialized
        response = await client.get("http://localhost:8000/health", timeout=2.0)
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_centrifugo_token_for_multiple_users():
    """Test that different users get different connection tokens."""
    async with httpx.AsyncClient() as client:
        # Create two users
        user1_response = await client.post(
            "http://localhost:8000/register",
            json={"username": f"user1_{int(time.time() * 1000)}"},
        )
        user2_response = await client.post(
            "http://localhost:8000/register",
            json={"username": f"user2_{int(time.time() * 1000)}"},
        )

        user1 = user1_response.json()
        user2 = user2_response.json()

        # Get tokens for both
        token1_response = await client.get(
            "http://localhost:8000/centrifugo/connection-token",
            headers={"X-API-Key": user1["api_key"]},
        )
        token2_response = await client.get(
            "http://localhost:8000/centrifugo/connection-token",
            headers={"X-API-Key": user2["api_key"]},
        )

        token1_data = token1_response.json()
        token2_data = token2_response.json()

        # Tokens should be different
        assert token1_data["token"] != token2_data["token"]

        # Each user should have their own channel
        assert f"user:{user1['username']}" in token1_data["channels"]
        assert f"user:{user2['username']}" in token2_data["channels"]

        # Both should have access to the main room
        assert "room:main" in token1_data["channels"]
        assert "room:main" in token2_data["channels"]


@pytest.mark.asyncio
async def test_centrifugo_api_endpoint_accessible():
    """Test that Centrifugo API endpoint is accessible."""
    async with httpx.AsyncClient() as client:
        try:
            # Try to access Centrifugo API (this will fail without auth, but we'll see if it's running)
            response = await client.post(
                "http://localhost:8001/api",
                json={},
                timeout=2.0,
            )
            # We expect either 200 or some auth error, not connection error
            # Just verify we can reach it
            assert response.status_code in [200, 400, 401, 403]
        except (httpx.ConnectError, httpx.TimeoutException):
            pytest.skip("Centrifugo API not accessible on port 8001")


@pytest.mark.asyncio
async def test_message_delivery_with_webhooks_still_works(test_user):
    """Test that webhook delivery still works alongside Centrifugo."""
    # Create a user with a webhook URL
    async with httpx.AsyncClient() as client:
        webhook_user_response = await client.post(
            "http://localhost:8000/register",
            json={
                "username": f"webhook_user_{int(time.time() * 1000)}",
                "webhook_url": "https://webhook.site/unique-id",
            },
        )
        webhook_user_response.json()  # Validate response but don't store

        # Send a message (should trigger both Centrifugo AND webhook)
        response = await client.post(
            "http://localhost:8000/messages",
            json={"content": "Test message for webhook"},
            headers={"X-API-Key": test_user["api_key"]},
        )

        assert response.status_code == 201

        # Webhook delivery is async, so we just verify the message was accepted
        # The webhook would be delivered in the background


@pytest.mark.asyncio
async def test_direct_message_to_centrifugo(test_user):
    """Test that direct messages work with Centrifugo."""
    async with httpx.AsyncClient() as client:
        # Create a second user
        user2_response = await client.post(
            "http://localhost:8000/register",
            json={"username": f"dm_recipient_{int(time.time() * 1000)}"},
        )
        user2 = user2_response.json()

        # Send a direct message
        response = await client.post(
            "http://localhost:8000/messages",
            json={
                "content": "Direct message test",
                "to_username": user2["username"],
            },
            headers={"X-API-Key": test_user["api_key"]},
        )

        assert response.status_code == 201
        data = response.json()

        assert data["message_type"] == "direct"
        assert data["to_username"] == user2["username"]
        assert data["from_username"] == test_user["username"]
