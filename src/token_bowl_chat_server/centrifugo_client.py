"""Centrifugo client for publishing messages."""

import logging
from datetime import UTC, datetime, timedelta

import jwt
from cent import AsyncClient

from .models import Message, MessageResponse, User

logger = logging.getLogger(__name__)


class CentrifugoClient:
    """Client for interacting with Centrifugo server."""

    def __init__(self, api_url: str, api_key: str, token_secret: str) -> None:
        """Initialize Centrifugo client.

        Args:
            api_url: Centrifugo HTTP API URL
            api_key: API key for authentication
            token_secret: Secret for generating JWT tokens
        """
        self.client = AsyncClient(api_url, api_key=api_key, timeout=3.0)
        self.token_secret = token_secret

    def generate_connection_token(self, user: User) -> str:
        """Generate JWT token for client connection.

        Args:
            user: User to generate token for

        Returns:
            JWT token string
        """
        claims = {
            "sub": user.username,  # User ID
            "exp": int((datetime.now(UTC) + timedelta(hours=24)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
        }
        return jwt.encode(claims, self.token_secret, algorithm="HS256")

    async def publish_room_message(self, message: Message, from_user: User) -> None:
        """Publish a room message to all subscribers.

        Args:
            message: Message to publish
            from_user: User who sent the message
        """
        message_data = MessageResponse.from_message(message, from_user=from_user).model_dump(
            mode="json"
        )

        try:
            await self.client.publish(channel="room:main", data=message_data)  # type: ignore[call-arg]
            logger.info(f"Published room message to Centrifugo: {message.id}")
        except Exception as e:
            logger.error(f"Failed to publish room message to Centrifugo: {e}")
            raise

    async def publish_direct_message(
        self, message: Message, from_user: User, to_user: User
    ) -> None:
        """Publish a direct message to specific user.

        Args:
            message: Message to publish
            from_user: User who sent the message
            to_user: User to receive the message
        """
        message_data = MessageResponse.from_message(
            message, from_user=from_user, to_user=to_user
        ).model_dump(mode="json")

        try:
            # Publish to user's personal channel
            await self.client.publish(channel=f"user:{to_user.username}", data=message_data)  # type: ignore[call-arg]
            logger.info(f"Published direct message to Centrifugo for {to_user.username}")
        except Exception as e:
            logger.error(f"Failed to publish direct message to Centrifugo: {e}")
            raise

    async def disconnect_user(self, username: str) -> None:
        """Disconnect a user from Centrifugo.

        Args:
            username: Username to disconnect
        """
        try:
            await self.client.disconnect(user=username)  # type: ignore[call-arg]
            logger.info(f"Disconnected {username} from Centrifugo")
        except Exception as e:
            logger.error(f"Failed to disconnect {username} from Centrifugo: {e}")


# Global singleton
centrifugo_client: CentrifugoClient | None = None


def get_centrifugo_client() -> CentrifugoClient:
    """Get the global Centrifugo client instance.

    Raises:
        RuntimeError: If Centrifugo client is not initialized
    """
    global centrifugo_client
    if centrifugo_client is None:
        raise RuntimeError("Centrifugo client not initialized")
    return centrifugo_client


def init_centrifugo_client(api_url: str, api_key: str, token_secret: str) -> None:
    """Initialize the global Centrifugo client.

    Args:
        api_url: Centrifugo HTTP API URL
        api_key: API key for authentication
        token_secret: Secret for generating JWT tokens
    """
    global centrifugo_client
    centrifugo_client = CentrifugoClient(api_url, api_key, token_secret)
    logger.info(f"Initialized Centrifugo client: {api_url}")
