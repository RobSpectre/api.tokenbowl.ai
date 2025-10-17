"""Tests for authentication module."""

import pytest
from fastapi import HTTPException

from token_bowl_chat_server.auth import generate_api_key, get_current_user, validate_api_key
from token_bowl_chat_server.models import User
from token_bowl_chat_server.storage import ChatStorage


def test_generate_api_key():
    """Test API key generation."""
    key1 = generate_api_key()
    key2 = generate_api_key()

    # Keys should be 64 characters (32 bytes hex)
    assert len(key1) == 64
    assert len(key2) == 64

    # Keys should be unique
    assert key1 != key2

    # Keys should be hexadecimal
    assert all(c in "0123456789abcdef" for c in key1)


@pytest.mark.asyncio
async def test_get_current_user_valid_key(test_storage):
    """Test getting current user with valid API key."""
    # Create a user
    api_key = generate_api_key()
    user = User(username="test_user", api_key=api_key)
    test_storage.add_user(user)

    # Get user with valid key
    result = await get_current_user(api_key=api_key)
    assert result.username == "test_user"


@pytest.mark.asyncio
async def test_get_current_user_missing_key():
    """Test getting current user with missing API key."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(api_key=None)

    assert exc_info.value.status_code == 401
    assert "Missing API key" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_invalid_key():
    """Test getting current user with invalid API key."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(api_key="invalid_key")

    assert exc_info.value.status_code == 401
    assert "Invalid API key" in exc_info.value.detail


def test_validate_api_key_valid(test_storage):
    """Test validate_api_key with valid key."""
    # Create a user
    api_key = generate_api_key()
    user = User(username="test_user", api_key=api_key)
    test_storage.add_user(user)

    # Validate
    result = validate_api_key(api_key)
    assert result is not None
    assert result.username == "test_user"


def test_validate_api_key_none():
    """Test validate_api_key with None."""
    result = validate_api_key(None)
    assert result is None


def test_validate_api_key_invalid():
    """Test validate_api_key with invalid key."""
    result = validate_api_key("invalid_key")
    assert result is None
