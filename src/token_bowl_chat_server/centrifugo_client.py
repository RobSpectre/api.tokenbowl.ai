"""Centrifugo client for publishing messages."""

import logging
from datetime import UTC, datetime, timedelta

import jwt
from cent import AsyncClient
from cent.dto import DisconnectRequest, PublishRequest

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
            # Grant subscription permissions for channels
            "channels": [
                "room:main",  # Allow subscribing to main room
                f"user:{user.username}",  # Allow subscribing to own user channel
            ],
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
            request = PublishRequest(channel="room:main", data=message_data)
            await self.client.publish(request)
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
            request = PublishRequest(channel=f"user:{to_user.username}", data=message_data)
            await self.client.publish(request)
            logger.info(f"Published direct message to Centrifugo for {to_user.username}")
        except Exception as e:
            logger.error(f"Failed to publish direct message to Centrifugo: {e}")
            raise

    async def publish_read_receipt(
        self, message_id: str, read_by: str, channel: str = "room:main"
    ) -> None:
        """Publish a read receipt event to Centrifugo.

        Args:
            message_id: ID of the message that was read
            read_by: Username who read the message
            channel: Channel to publish to (default: room:main)
        """
        receipt_data = {
            "type": "read_receipt",
            "message_id": message_id,
            "read_by": read_by,
            "read_at": datetime.now(UTC).isoformat(),
        }

        try:
            request = PublishRequest(channel=channel, data=receipt_data)
            await self.client.publish(request)
            logger.info(f"Published read receipt to Centrifugo: {message_id} read by {read_by}")
        except Exception as e:
            logger.error(f"Failed to publish read receipt to Centrifugo: {e}")

    async def publish_typing_indicator(self, username: str, to_username: str | None = None) -> None:
        """Publish a typing indicator event to Centrifugo.

        Args:
            username: Username who is typing
            to_username: Optional recipient for direct message typing
        """
        typing_data = {
            "type": "typing",
            "username": username,
            "to_username": to_username,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Determine which channel to publish to
        channel = f"user:{to_username}" if to_username else "room:main"

        try:
            request = PublishRequest(channel=channel, data=typing_data)
            await self.client.publish(request)
            logger.debug(
                f"Published typing indicator: {username} typing to {to_username or 'room'}"
            )
        except Exception as e:
            logger.error(f"Failed to publish typing indicator to Centrifugo: {e}")

    async def publish_unread_count(
        self, username: str, unread_room: int, unread_direct: int
    ) -> None:
        """Publish unread count update to a user's channel.

        Args:
            username: Username to send update to
            unread_room: Number of unread room messages
            unread_direct: Number of unread direct messages
        """
        unread_data = {
            "type": "unread_count",
            "unread_room_messages": unread_room,
            "unread_direct_messages": unread_direct,
            "total_unread": unread_room + unread_direct,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            # Send to user's personal channel
            request = PublishRequest(channel=f"user:{username}", data=unread_data)
            await self.client.publish(request)
            logger.debug(
                f"Published unread count to {username}: {unread_room + unread_direct} total"
            )
        except Exception as e:
            logger.error(f"Failed to publish unread count to Centrifugo: {e}")

    async def disconnect_user(self, username: str) -> None:
        """Disconnect a user from Centrifugo.

        Args:
            username: Username to disconnect
        """
        try:
            request = DisconnectRequest(user=username)
            await self.client.disconnect(request)
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
