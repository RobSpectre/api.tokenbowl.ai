"""Webhook delivery system for sending messages to LLMs."""

import asyncio
import logging
from typing import Optional

import httpx

from .models import Message, MessageResponse, User

logger = logging.getLogger(__name__)


class WebhookDelivery:
    """Handles webhook delivery to users."""

    def __init__(self, timeout: float = 10.0, max_retries: int = 3) -> None:
        """Initialize webhook delivery system.

        Args:
            timeout: Timeout for webhook requests in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Start the webhook delivery system."""
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def stop(self) -> None:
        """Stop the webhook delivery system."""
        if self.client:
            await self.client.aclose()
            self.client = None

    async def deliver_message(self, user: User, message: Message) -> bool:
        """Deliver a message to a user's webhook URL.

        Args:
            user: User to deliver message to
            message: Message to deliver

        Returns:
            True if delivery was successful, False otherwise
        """
        if not user.webhook_url:
            logger.debug(f"User {user.username} has no webhook URL configured")
            return False

        if not self.client:
            logger.error("Webhook client not initialized")
            return False

        # Fetch sender user info for display
        from .storage import storage
        from_user = storage.get_user_by_username(message.from_username)
        message_data = MessageResponse.from_message(message, from_user=from_user).model_dump()

        for attempt in range(self.max_retries):
            try:
                response = await self.client.post(
                    str(user.webhook_url),
                    json=message_data,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code < 300:
                    logger.info(
                        f"Successfully delivered message to {user.username} at {user.webhook_url}"
                    )
                    return True
                else:
                    logger.warning(
                        f"Webhook delivery to {user.username} failed with status "
                        f"{response.status_code} (attempt {attempt + 1}/{self.max_retries})"
                    )

            except httpx.TimeoutException:
                logger.warning(
                    f"Webhook delivery to {user.username} timed out "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
            except httpx.RequestError as e:
                logger.warning(
                    f"Webhook delivery to {user.username} failed: {e} "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error delivering to {user.username}: {e} "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )

            # Wait before retrying (exponential backoff)
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2**attempt)

        logger.error(
            f"Failed to deliver message to {user.username} after {self.max_retries} attempts"
        )
        return False

    async def broadcast_to_webhooks(
        self, message: Message, users: list[User], exclude_username: Optional[str] = None
    ) -> None:
        """Broadcast a message to multiple users via webhooks.

        Args:
            message: Message to broadcast
            users: List of users to send to
            exclude_username: Username to exclude from broadcast (e.g., the sender)
        """
        tasks = []
        for user in users:
            if exclude_username and user.username == exclude_username:
                continue

            if user.webhook_url:
                tasks.append(self.deliver_message(user, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


# Global webhook delivery instance
webhook_delivery = WebhookDelivery()
