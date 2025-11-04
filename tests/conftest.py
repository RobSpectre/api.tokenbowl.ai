"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient

from token_bowl_chat_server import api as api_module
from token_bowl_chat_server import auth as auth_module
from token_bowl_chat_server import centrifugo_client as centrifugo_module
from token_bowl_chat_server import storage as storage_module
from token_bowl_chat_server.config import settings
from token_bowl_chat_server.server import create_app
from token_bowl_chat_server.storage import ChatStorage


@pytest.fixture(autouse=True)
def test_storage():
    """Create a fresh in-memory SQLite storage for each test."""
    # Create new in-memory storage
    test_storage_instance = ChatStorage(db_path=":memory:")

    # Replace global storage with test storage in all modules that import it
    original_storage = storage_module.storage
    storage_module.storage = test_storage_instance
    api_module.storage = test_storage_instance
    auth_module.storage = test_storage_instance

    yield test_storage_instance

    # Restore original storage after test
    storage_module.storage = original_storage
    api_module.storage = original_storage
    auth_module.storage = original_storage


@pytest.fixture(autouse=True)
def test_centrifugo():
    """Mock Centrifugo client for tests."""
    from unittest.mock import AsyncMock, MagicMock

    from token_bowl_chat_server.centrifugo_client import CentrifugoClient

    # Create a mock Centrifugo client that doesn't require an event loop
    mock_client = MagicMock(spec=CentrifugoClient)
    mock_client.token_secret = settings.centrifugo_token_secret
    mock_client.generate_connection_token = lambda user: __import__("jwt").encode(
        {
            "sub": user.username,
            "exp": int(
                (
                    __import__("datetime").datetime.now(__import__("datetime").UTC)
                    + __import__("datetime").timedelta(hours=24)
                ).timestamp()
            ),
            "iat": int(__import__("datetime").datetime.now(__import__("datetime").UTC).timestamp()),
        },
        settings.centrifugo_token_secret,
        algorithm="HS256",
    )
    mock_client.publish_room_message = AsyncMock()
    mock_client.publish_direct_message = AsyncMock()
    mock_client.disconnect_user = AsyncMock()
    # Add mock .client attribute for testing disconnect
    mock_client.client = MagicMock()
    mock_client.client.disconnect = AsyncMock()

    # Set as global instance
    centrifugo_module.centrifugo_client = mock_client

    yield mock_client

    # Reset to None after test
    centrifugo_module.centrifugo_client = None


@pytest.fixture
def app(test_storage):
    """Create a fresh FastAPI app for testing."""
    return create_app()


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def registered_user(client):
    """Register a test user and return registration data."""
    response = client.post(
        "/register",
        json={"username": "test_user", "webhook_url": None},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def registered_user2(client):
    """Register a second test user."""
    response = client.post(
        "/register",
        json={"username": "test_user2", "webhook_url": None},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def registered_admin(client):
    """Register an admin user."""
    response = client.post(
        "/register",
        json={"username": "admin_user", "webhook_url": None, "admin": True},
    )
    assert response.status_code == 201
    return response.json()
