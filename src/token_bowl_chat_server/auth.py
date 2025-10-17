"""Authentication utilities for API key validation."""

import secrets
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .models import User
from .storage import storage

# API key header configuration
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def generate_api_key() -> str:
    """Generate a secure random API key.

    Returns:
        A 64-character hexadecimal API key
    """
    return secrets.token_hex(32)


async def get_current_user(api_key: str = Security(api_key_header)) -> User:
    """Validate API key and return current user.

    Args:
        api_key: API key from request header

    Returns:
        Authenticated user

    Raises:
        HTTPException: If API key is invalid or missing
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    user = storage.get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return user


def validate_api_key(api_key: Optional[str]) -> Optional[User]:
    """Validate API key without raising exceptions.

    Args:
        api_key: API key to validate

    Returns:
        User if valid, None otherwise
    """
    if not api_key:
        return None

    return storage.get_user_by_api_key(api_key)
