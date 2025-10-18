"""Tests for server startup and shutdown lifecycle."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from token_bowl_chat_server.server import create_app, lifespan


@pytest.mark.asyncio
async def test_lifespan_startup_and_shutdown():
    """Test that the lifespan context manager starts and stops webhook delivery."""
    from token_bowl_chat_server import webhook

    app = create_app()

    # Mock webhook_delivery start and stop methods
    with patch.object(webhook.webhook_delivery, "start", new_callable=AsyncMock) as mock_start:
        with patch.object(webhook.webhook_delivery, "stop", new_callable=AsyncMock) as mock_stop:
            # Enter the lifespan context
            async with lifespan(app):
                # Verify start was called
                mock_start.assert_called_once()

            # After exiting context, verify stop was called
            mock_stop.assert_called_once()


@pytest.mark.asyncio
async def test_create_app():
    """Test that create_app creates a properly configured FastAPI app."""
    app = create_app()

    assert app.title == "Token Bowl Chat Server"
    assert app.version == "0.1.0"
    assert "A chat server designed for large language model consumption" in app.description


def test_static_files_served_in_dev_mode():
    """Test that static files are served when in dev mode (reload=True)."""
    from token_bowl_chat_server import config

    # Ensure we're in dev mode
    original_reload = config.settings.reload
    config.settings.reload = True

    try:
        app = create_app()
        client = TestClient(app)

        # Test accessing a static file
        response = client.get("/public/images/claude-color.png")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/")
    finally:
        config.settings.reload = original_reload


def test_static_files_not_served_in_production():
    """Test that static files are not mounted when in production mode (reload=False)."""
    from token_bowl_chat_server import config

    # Simulate production mode
    original_reload = config.settings.reload
    config.settings.reload = False

    try:
        app = create_app()
        client = TestClient(app)

        # Try to access a static file - should get 404
        response = client.get("/public/images/claude-color.png")
        assert response.status_code == 404
    finally:
        config.settings.reload = original_reload
