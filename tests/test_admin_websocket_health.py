"""Tests for admin WebSocket connections health endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient

from token_bowl_chat_server.models import User
from token_bowl_chat_server.websocket import connection_manager
from token_bowl_chat_server.websocket_heartbeat import heartbeat_manager


@pytest.mark.asyncio
async def test_admin_websocket_connections_endpoint(client: TestClient, registered_admin: dict):
    """Test the admin WebSocket connections endpoint with multiple connections."""
    # Clear any existing connections
    connection_manager.active_connections.clear()
    heartbeat_manager.active_connections.clear()

    # Create test users
    user1 = User(username="ws_user1", api_key="a" * 64)
    user2 = User(username="ws_user2", api_key="b" * 64)

    # Create mock WebSocket connections
    ws1_user1 = MagicMock(spec=WebSocket)
    ws1_user1.accept = AsyncMock()
    ws1_user1.client = MagicMock()
    ws1_user1.client.host = "host1"

    ws2_user1 = MagicMock(spec=WebSocket)
    ws2_user1.accept = AsyncMock()
    ws2_user1.client = MagicMock()
    ws2_user1.client.host = "host2"

    ws1_user2 = MagicMock(spec=WebSocket)
    ws1_user2.accept = AsyncMock()
    ws1_user2.client = MagicMock()
    ws1_user2.client.host = "host3"

    # Connect websockets (user1 has 2 connections, user2 has 1)
    with patch("token_bowl_chat_server.websocket.heartbeat_manager"):
        await connection_manager.connect(ws1_user1, user1)
        await connection_manager.connect(ws2_user1, user1)  # Second connection for user1
        await connection_manager.connect(ws1_user2, user2)

    # Manually track connections in heartbeat manager for testing
    heartbeat_manager.track_connection(user1.username, ws1_user1)
    heartbeat_manager.track_connection(user1.username, ws2_user1)
    heartbeat_manager.track_connection(user2.username, ws1_user2)

    # Call the admin endpoint
    response = client.get(
        "/admin/websocket/connections",
        headers={"X-API-Key": registered_admin["api_key"]},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "total_users" in data
    assert "total_connections" in data
    assert "connections" in data

    # Verify counts
    assert data["total_users"] == 2  # 2 unique users
    assert data["total_connections"] == 3  # 3 total connections

    # Verify connections data
    connections = data["connections"]
    assert len(connections) == 3

    # Each connection should have expected fields
    for conn in connections:
        assert "username" in conn
        assert "connection_id" in conn
        assert "last_activity" in conn
        assert "last_pong" in conn
        assert "seconds_since_activity" in conn
        assert "seconds_since_pong" in conn
        assert "is_healthy" in conn

    # Verify usernames
    usernames = [conn["username"] for conn in connections]
    assert usernames.count("ws_user1") == 2  # user1 has 2 connections
    assert usernames.count("ws_user2") == 1  # user2 has 1 connection

    # Clean up
    connection_manager.active_connections.clear()
    heartbeat_manager.active_connections.clear()
    heartbeat_manager.heartbeat_tasks.clear()


@pytest.mark.asyncio
async def test_admin_websocket_connections_empty(client: TestClient, registered_admin: dict):
    """Test the admin WebSocket connections endpoint with no connections."""
    # Clear any existing connections
    connection_manager.active_connections.clear()
    heartbeat_manager.active_connections.clear()

    response = client.get(
        "/admin/websocket/connections",
        headers={"X-API-Key": registered_admin["api_key"]},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total_users"] == 0
    assert data["total_connections"] == 0
    assert data["connections"] == []


def test_admin_websocket_connections_requires_admin(client: TestClient, registered_user: dict):
    """Test that the WebSocket connections endpoint requires admin privileges."""
    response = client.get(
        "/admin/websocket/connections",
        headers={"X-API-Key": registered_user["api_key"]},
    )

    assert response.status_code == 403
    assert "Admin privileges required" in response.json()["detail"]


def test_admin_websocket_connections_requires_auth(client: TestClient):
    """Test that the WebSocket connections endpoint requires authentication."""
    response = client.get("/admin/websocket/connections")

    assert response.status_code == 401
    assert response.json()["detail"] in [
        "Not authenticated",
        "Invalid or missing authentication credentials",
    ]
