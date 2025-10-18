"""Stytch client wrapper for authentication."""

import logging
from typing import Optional

import stytch
from stytch.core.response_base import StytchError

from .config import settings

logger = logging.getLogger(__name__)


class StytchClient:
    """Wrapper for Stytch authentication operations."""

    def __init__(self) -> None:
        """Initialize Stytch client."""
        self._client: Optional[stytch.Client] = None

        if settings.stytch_enabled:
            try:
                # Validate that we have both project_id and secret
                if not settings.stytch_project_id or not settings.stytch_secret:
                    logger.error(
                        "Stytch project_id and secret are required. "
                        "Set STYTCH_PROJECT_ID and STYTCH_SECRET environment variables."
                    )
                    return

                # Use normalized environment (test or live only)
                env = settings.stytch_env_normalized
                self._client = stytch.Client(
                    project_id=settings.stytch_project_id,
                    secret=settings.stytch_secret,
                    environment=env,  # type: ignore
                )
                logger.info(f"Stytch client initialized successfully in {env} mode")
            except Exception as e:
                logger.error(f"Failed to initialize Stytch client: {e}")
                self._client = None

    @property
    def enabled(self) -> bool:
        """Check if Stytch is enabled and initialized."""
        return self._client is not None

    async def send_magic_link(self, email: str, signup_magic_link_url: str) -> bool:
        """Send a magic link to the user's email.

        Args:
            email: User's email address
            signup_magic_link_url: URL to redirect to after clicking magic link

        Returns:
            True if magic link was sent successfully

        Raises:
            RuntimeError: If Stytch is not enabled
            StytchError: If Stytch API call fails
        """
        if not self._client:
            raise RuntimeError("Stytch is not enabled")

        try:
            # Use async method in SDK v6+
            response = await self._client.magic_links.email.login_or_create_async(
                email=email,
                login_magic_link_url=signup_magic_link_url,
                signup_magic_link_url=signup_magic_link_url,
            )
            logger.info(f"Magic link sent to {email}")
            return True
        except StytchError as e:
            logger.error(f"Failed to send magic link: {e}")
            raise

    async def authenticate_magic_link(self, token: str) -> tuple[str, str, str]:
        """Authenticate a magic link token.

        Args:
            token: Magic link token from URL

        Returns:
            Tuple of (stytch_user_id, email, session_token)

        Raises:
            RuntimeError: If Stytch is not enabled
            StytchError: If authentication fails
        """
        if not self._client:
            raise RuntimeError("Stytch is not enabled")

        try:
            # Use async method in SDK v6+
            response = await self._client.magic_links.authenticate_async(token=token)

            # Extract user information
            stytch_user_id = response.user_id
            email = response.user.emails[0].email if response.user.emails else ""
            session_token = response.session_token

            logger.info(f"Successfully authenticated user {stytch_user_id}")
            return (stytch_user_id, email, session_token)

        except StytchError as e:
            logger.error(f"Failed to authenticate magic link: {e}")
            raise

    async def validate_session(self, session_token: str) -> Optional[str]:
        """Validate a Stytch session token.

        Args:
            session_token: Stytch session token to validate

        Returns:
            Stytch user ID if valid, None otherwise
        """
        if not self._client:
            return None

        try:
            # Use async method in SDK v6+
            response = await self._client.sessions.authenticate_async(session_token=session_token)
            return response.user_id
        except StytchError as e:
            logger.debug(f"Session validation failed: {e}")
            return None


# Global Stytch client instance
stytch_client = StytchClient()
