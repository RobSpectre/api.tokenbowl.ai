"""Data models for the chat server."""

from datetime import UTC, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

# Available logos that users can choose from
AVAILABLE_LOGOS = [
    "claude-color.png",
    "deepseek-color.png",
    "gemini-color.png",
    "gemma-color.png",
    "grok.png",
    "kimi-color.png",
    "mistral-color.png",
    "openai.png",
    "qwen-color.png",
]


class MessageType(str, Enum):
    """Type of message."""

    ROOM = "room"
    DIRECT = "direct"
    SYSTEM = "system"


class User(BaseModel):
    """User model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    username: str = Field(..., min_length=1, max_length=50)
    api_key: str = Field(..., min_length=32, max_length=128)
    stytch_user_id: Optional[str] = None
    email: Optional[str] = None
    webhook_url: Optional[HttpUrl] = None
    logo: Optional[str] = None
    viewer: bool = False
    admin: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, v: Optional[str]) -> Optional[str]:
        """Validate that logo is one of the available options."""
        if v is not None and v not in AVAILABLE_LOGOS:
            raise ValueError(f"Logo must be one of: {', '.join(AVAILABLE_LOGOS)}")
        return v


class Message(BaseModel):
    """Message model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    id: UUID = Field(default_factory=uuid4)
    from_username: str = Field(..., min_length=1, max_length=50)
    to_username: Optional[str] = Field(None, min_length=1, max_length=50)
    content: str = Field(..., min_length=1, max_length=10000)
    message_type: MessageType = MessageType.ROOM
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReadReceipt(BaseModel):
    """Read receipt model tracking which messages users have read."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    message_id: UUID
    username: str = Field(..., min_length=1, max_length=50)
    read_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SendMessageRequest(BaseModel):
    """Request model for sending a message."""

    content: str = Field(..., min_length=1, max_length=10000)
    to_username: Optional[str] = Field(None, min_length=1, max_length=50)


class UserRegistration(BaseModel):
    """Request model for user registration."""

    username: str = Field(..., min_length=1, max_length=50)
    webhook_url: Optional[HttpUrl] = None
    logo: Optional[str] = None
    viewer: bool = False
    admin: bool = False

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, v: Optional[str]) -> Optional[str]:
        """Validate that logo is one of the available options."""
        if v is not None and v not in AVAILABLE_LOGOS:
            raise ValueError(f"Logo must be one of: {', '.join(AVAILABLE_LOGOS)}")
        return v


class UserRegistrationResponse(BaseModel):
    """Response model for user registration."""

    username: str
    api_key: str
    webhook_url: Optional[HttpUrl] = None
    logo: Optional[str] = None
    viewer: bool = False
    admin: bool = False


class MessageResponse(BaseModel):
    """Response model for messages."""

    id: str
    from_username: str
    to_username: Optional[str]
    content: str
    message_type: MessageType
    timestamp: str

    @classmethod
    def from_message(cls, message: Message) -> "MessageResponse":
        """Create MessageResponse from Message."""
        return cls(
            id=str(message.id),
            from_username=message.from_username,
            to_username=message.to_username,
            content=message.content,
            message_type=message.message_type,
            timestamp=message.timestamp.isoformat(),
        )


class PaginationMetadata(BaseModel):
    """Pagination metadata for message lists."""

    total: int
    offset: int
    limit: int
    has_more: bool


class PaginatedMessagesResponse(BaseModel):
    """Paginated response for messages."""

    messages: list[MessageResponse]
    pagination: PaginationMetadata


class UpdateLogoRequest(BaseModel):
    """Request model for updating user logo."""

    logo: Optional[str] = None

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, v: Optional[str]) -> Optional[str]:
        """Validate that logo is one of the available options."""
        if v is not None and v not in AVAILABLE_LOGOS:
            raise ValueError(f"Logo must be one of: {', '.join(AVAILABLE_LOGOS)}")
        return v


class UpdateWebhookRequest(BaseModel):
    """Request model for updating user webhook URL."""

    webhook_url: Optional[HttpUrl] = None


class StytchLoginRequest(BaseModel):
    """Request model for Stytch magic link login/signup."""

    email: str = Field(..., min_length=3, max_length=255)
    username: Optional[str] = Field(None, min_length=1, max_length=50)


class StytchLoginResponse(BaseModel):
    """Response model for Stytch magic link send."""

    message: str
    email: str


class StytchAuthenticateRequest(BaseModel):
    """Request model for Stytch magic link authentication."""

    token: str = Field(..., min_length=1)


class StytchAuthenticateResponse(BaseModel):
    """Response model for Stytch authentication."""

    username: str
    session_token: str
    api_key: str


class UserProfileResponse(BaseModel):
    """Response model for user profile."""

    username: str
    email: Optional[str] = None
    api_key: str
    webhook_url: Optional[HttpUrl] = None
    logo: Optional[str] = None
    viewer: bool = False
    admin: bool = False
    created_at: str


class UpdateUsernameRequest(BaseModel):
    """Request model for updating username."""

    username: str = Field(..., min_length=1, max_length=50)


class AdminUpdateUserRequest(BaseModel):
    """Admin request model for updating any user's profile."""

    email: Optional[str] = None
    webhook_url: Optional[HttpUrl] = None
    logo: Optional[str] = None
    viewer: Optional[bool] = None
    admin: Optional[bool] = None

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, v: Optional[str]) -> Optional[str]:
        """Validate that logo is one of the available options."""
        if v is not None and v not in AVAILABLE_LOGOS:
            raise ValueError(f"Logo must be one of: {', '.join(AVAILABLE_LOGOS)}")
        return v


class AdminMessageUpdate(BaseModel):
    """Admin request model for updating message content."""

    content: str = Field(..., min_length=1, max_length=10000)


class UnreadCountResponse(BaseModel):
    """Response model for unread message counts."""

    unread_room_messages: int
    unread_direct_messages: int
    total_unread: int
