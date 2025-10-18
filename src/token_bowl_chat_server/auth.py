"""Authentication utilities for API key and Stytch validation."""

import secrets
from typing import Optional

from fastapi import Header, HTTPException, Security, status
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


async def get_current_user(
    api_key: Optional[str] = Security(api_key_header),
    authorization: Optional[str] = Header(default=None),
) -> User:
    """Validate API key or Stytch session token and return current user.

    Supports dual authentication:
    - API key via X-API-Key header (for programmatic access)
    - Stytch session token via Authorization: Bearer <token> header (for human users)

    Args:
        api_key: API key from X-API-Key header
        authorization: Authorization header (Bearer token)

    Returns:
        Authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    # Try API key authentication first
    if api_key:
        user = storage.get_user_by_api_key(api_key)
        if user:
            return user

    # Try Stytch session token authentication
    if authorization and authorization.startswith("Bearer "):
        from .stytch_client import stytch_client

        session_token = authorization[7:]  # Remove "Bearer " prefix
        stytch_user_id = await stytch_client.validate_session(session_token)

        if stytch_user_id:
            user = storage.get_user_by_stytch_id(stytch_user_id)
            if user:
                return user

    # No valid authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


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


async def get_current_admin(current_user: User = Security(get_current_user)) -> User:
    """Validate that current user is an admin.

    Args:
        current_user: Authenticated user

    Returns:
        User if they are an admin

    Raises:
        HTTPException: If user is not an admin
    """
    if not current_user.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
