"""Tests for server startup and shutdown lifecycle."""

import pytest
from unittest.mock import AsyncMock, patch

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
