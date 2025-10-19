"""Authentication utilities for API key and Stytch validation."""

import secrets
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .models import Permission, User
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
    api_key: str | None = Security(api_key_header),
    authorization: str | None = Header(default=None),
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


def validate_api_key(api_key: str | None) -> User | None:
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

    DEPRECATED: Use require_permission(Permission.ADMIN_ACCESS) instead.

    Args:
        current_user: Authenticated user

    Returns:
        User if they are an admin

    Raises:
        HTTPException: If user is not an admin
    """
    if not current_user.has_permission(Permission.ADMIN_ACCESS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def require_permission(permission: Permission) -> Callable:
    """Create a dependency that requires a specific permission.

    Usage:
        @router.delete("/admin/users/{username}")
        async def delete_user(
            username: str,
            user: User = Depends(require_permission(Permission.DELETE_USER))
        ):
            # User has DELETE_USER permission
            ...

    Args:
        permission: The permission required to access the endpoint

    Returns:
        A FastAPI dependency function that checks the permission
    """

    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        """Check if current user has the required permission.

        Args:
            current_user: Authenticated user

        Returns:
            User if they have the permission

        Raises:
            HTTPException: If user lacks the permission
        """
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission.value}' required. Your role '{current_user.role.value}' does not have this permission.",
            )
        return current_user

    return permission_checker


def require_any_permission(*permissions: Permission) -> Callable:
    """Create a dependency that requires any one of the specified permissions.

    Usage:
        @router.get("/messages")
        async def get_messages(
            user: User = Depends(require_any_permission(
                Permission.READ_MESSAGES,
                Permission.ADMIN_ACCESS
            ))
        ):
            ...

    Args:
        *permissions: One or more permissions, any of which satisfies the requirement

    Returns:
        A FastAPI dependency function that checks if user has any of the permissions
    """

    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        """Check if current user has any of the required permissions.

        Args:
            current_user: Authenticated user

        Returns:
            User if they have at least one permission

        Raises:
            HTTPException: If user lacks all permissions
        """
        if any(current_user.has_permission(perm) for perm in permissions):
            return current_user

        perm_names = ", ".join([p.value for p in permissions])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of these permissions required: {perm_names}. Your role '{current_user.role.value}' does not have any of them.",
        )

    return permission_checker
