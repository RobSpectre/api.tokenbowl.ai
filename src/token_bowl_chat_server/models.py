"""Data models for the chat server."""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

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


class Role(str, Enum):
    """User roles for authorization."""

    ADMIN = "admin"  # Full CRUD access to all resources
    MEMBER = "member"  # Default role - can send/receive messages, update own profile
    VIEWER = "viewer"  # Read-only access - cannot send DMs or update profile
    BOT = "bot"  # Automated agents - can send room messages only


class Permission(str, Enum):
    """Granular permissions for authorization."""

    # Message permissions
    READ_MESSAGES = "messages:read"
    SEND_ROOM_MESSAGE = "messages:send:room"
    SEND_DIRECT_MESSAGE = "messages:send:direct"
    UPDATE_ANY_MESSAGE = "messages:update:any"
    DELETE_ANY_MESSAGE = "messages:delete:any"

    # User permissions
    READ_USERS = "users:read"
    UPDATE_OWN_PROFILE = "users:update:own"
    UPDATE_ANY_USER = "users:update:any"
    DELETE_USER = "users:delete"
    ASSIGN_ROLES = "users:assign_roles"

    # Bot permissions
    CREATE_BOT = "bots:create"
    UPDATE_OWN_BOT = "bots:update:own"
    DELETE_OWN_BOT = "bots:delete:own"
    UPDATE_ANY_BOT = "bots:update:any"
    DELETE_ANY_BOT = "bots:delete:any"

    # Admin permissions
    ADMIN_ACCESS = "admin:access"


# Role to permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        # Admins have all permissions
        Permission.READ_MESSAGES,
        Permission.SEND_ROOM_MESSAGE,
        Permission.SEND_DIRECT_MESSAGE,
        Permission.UPDATE_ANY_MESSAGE,
        Permission.DELETE_ANY_MESSAGE,
        Permission.READ_USERS,
        Permission.UPDATE_OWN_PROFILE,
        Permission.UPDATE_ANY_USER,
        Permission.DELETE_USER,
        Permission.ASSIGN_ROLES,
        Permission.CREATE_BOT,
        Permission.UPDATE_OWN_BOT,
        Permission.DELETE_OWN_BOT,
        Permission.UPDATE_ANY_BOT,
        Permission.DELETE_ANY_BOT,
        Permission.ADMIN_ACCESS,
    },
    Role.MEMBER: {
        # Members can do everything except admin functions
        Permission.READ_MESSAGES,
        Permission.SEND_ROOM_MESSAGE,
        Permission.SEND_DIRECT_MESSAGE,
        Permission.READ_USERS,
        Permission.UPDATE_OWN_PROFILE,
        Permission.CREATE_BOT,
        Permission.UPDATE_OWN_BOT,
        Permission.DELETE_OWN_BOT,
    },
    Role.VIEWER: {
        # Viewers can only read
        Permission.READ_MESSAGES,
        Permission.READ_USERS,
    },
    Role.BOT: {
        # Bots can read and send room messages only
        Permission.READ_MESSAGES,
        Permission.SEND_ROOM_MESSAGE,
        Permission.READ_USERS,
        Permission.UPDATE_OWN_PROFILE,
    },
}


class User(BaseModel):
    """User model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    id: UUID = Field(default_factory=uuid4)  # Primary key
    username: str = Field(..., min_length=1, max_length=50)
    api_key: str = Field(..., min_length=32, max_length=128)
    role: Role = Role.MEMBER  # New role-based authorization
    created_by: UUID | None = None  # User ID of creator (only for bots)
    stytch_user_id: str | None = None
    email: str | None = None
    webhook_url: HttpUrl | None = None
    logo: str | None = None
    # Legacy fields for backward compatibility - will be removed in future
    viewer: bool = False
    admin: bool = False
    bot: bool = False
    emoji: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, v: str | None) -> str | None:
        """Validate that logo is one of the available options."""
        if v is not None and v not in AVAILABLE_LOGOS:
            raise ValueError(f"Logo must be one of: {', '.join(AVAILABLE_LOGOS)}")
        return v

    @field_validator("emoji")
    @classmethod
    def validate_emoji(cls, v: str | None) -> str | None:
        """Validate that emoji is a single character."""
        if v is not None and len(v) > 10:  # Allow up to 10 chars for complex emojis
            raise ValueError("Emoji must be 10 characters or less")
        return v

    @model_validator(mode="after")
    def sync_role_with_legacy_fields(self) -> "User":
        """Ensure role is consistent with legacy boolean fields.

        This maintains backward compatibility while transitioning to role-based auth.
        Role takes precedence, and legacy fields are synced to match.
        """
        # Sync legacy fields based on role
        self.admin = self.role == Role.ADMIN
        self.viewer = self.role == Role.VIEWER
        self.bot = self.role == Role.BOT
        return self

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission.

        Args:
            permission: The permission to check

        Returns:
            True if user's role grants the permission
        """
        return permission in ROLE_PERMISSIONS.get(self.role, set())


class Message(BaseModel):
    """Message model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    id: UUID = Field(default_factory=uuid4)
    from_username: str = Field(..., min_length=1, max_length=50)
    to_username: str | None = Field(None, min_length=1, max_length=50)
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
    to_username: str | None = Field(None, min_length=1, max_length=50)


class UserRegistration(BaseModel):
    """Request model for user registration."""

    username: str = Field(..., min_length=1, max_length=50)
    webhook_url: HttpUrl | None = None
    logo: str | None = None
    role: Role | None = None  # Explicit role assignment (optional)
    # Legacy fields - will derive role if not explicitly set
    viewer: bool = False
    admin: bool = False
    bot: bool = False
    emoji: str | None = None

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, v: str | None) -> str | None:
        """Validate that logo is one of the available options."""
        if v is not None and v not in AVAILABLE_LOGOS:
            raise ValueError(f"Logo must be one of: {', '.join(AVAILABLE_LOGOS)}")
        return v

    @field_validator("emoji")
    @classmethod
    def validate_emoji(cls, v: str | None) -> str | None:
        """Validate that emoji is a single character."""
        if v is not None and len(v) > 10:  # Allow up to 10 chars for complex emojis
            raise ValueError("Emoji must be 10 characters or less")
        return v

    @model_validator(mode="after")
    def validate_bot_cannot_have_logo(self):
        """Validate that bots cannot have logos."""
        if self.bot and self.logo is not None:
            raise ValueError("Bots can only use emoji for avatars, not logos")
        return self

    def get_role(self) -> Role:
        """Determine role from registration data.

        Priority:
        1. Explicit role field if provided
        2. Derive from legacy boolean fields (admin > viewer > bot > member)

        Returns:
            The appropriate role for this user
        """
        if self.role is not None:
            return self.role

        # Derive role from legacy fields
        if self.admin:
            return Role.ADMIN
        elif self.viewer:
            return Role.VIEWER
        elif self.bot:
            return Role.BOT
        else:
            return Role.MEMBER


class UserRegistrationResponse(BaseModel):
    """Response model for user registration."""

    id: str  # UUID as string
    username: str
    api_key: str
    role: Role
    webhook_url: HttpUrl | None = None
    logo: str | None = None
    viewer: bool = False
    admin: bool = False
    bot: bool = False
    emoji: str | None = None


class MessageResponse(BaseModel):
    """Response model for messages."""

    id: str  # Message UUID as string
    from_user_id: str  # User UUID as string
    from_username: str
    from_user_logo: str | None = None
    from_user_emoji: str | None = None
    from_user_bot: bool = False
    to_user_id: str | None = None  # User UUID as string
    to_username: str | None = None
    content: str
    message_type: MessageType
    timestamp: str

    @classmethod
    def from_message(
        cls, message: Message, from_user: User | None = None, to_user: User | None = None
    ) -> "MessageResponse":
        """Create MessageResponse from Message.

        Args:
            message: The message to convert
            from_user: Optional user object to include display info (logo, emoji, bot)
                      If not provided, these fields will be None/False
            to_user: Optional recipient user object to include their ID
                      If not provided, to_user_id will be None
        """
        return cls(
            id=str(message.id),
            from_user_id=str(from_user.id) if from_user else "",
            from_username=message.from_username,
            from_user_logo=from_user.logo if from_user else None,
            from_user_emoji=from_user.emoji if from_user else None,
            from_user_bot=from_user.bot if from_user else False,
            to_user_id=str(to_user.id) if to_user else None,
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

    logo: str | None = None

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, v: str | None) -> str | None:
        """Validate that logo is one of the available options."""
        if v is not None and v not in AVAILABLE_LOGOS:
            raise ValueError(f"Logo must be one of: {', '.join(AVAILABLE_LOGOS)}")
        return v


class UpdateWebhookRequest(BaseModel):
    """Request model for updating user webhook URL."""

    webhook_url: HttpUrl | None = None


class StytchLoginRequest(BaseModel):
    """Request model for Stytch magic link login/signup."""

    email: str = Field(..., min_length=3, max_length=255)
    username: str | None = Field(None, min_length=1, max_length=50)


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


class PublicUserProfile(BaseModel):
    """Public user profile (no sensitive information)."""

    id: str  # UUID as string
    username: str
    role: Role
    logo: str | None = None
    emoji: str | None = None
    bot: bool = False
    viewer: bool = False


class UserProfileResponse(BaseModel):
    """Response model for user profile."""

    id: str  # UUID as string
    username: str
    role: Role
    email: str | None = None
    api_key: str
    webhook_url: HttpUrl | None = None
    logo: str | None = None
    viewer: bool = False
    admin: bool = False
    bot: bool = False
    emoji: str | None = None
    created_at: str


class UpdateUsernameRequest(BaseModel):
    """Request model for updating username."""

    username: str = Field(..., min_length=1, max_length=50)


class AdminUpdateUserRequest(BaseModel):
    """Admin request model for updating any user's profile."""

    username: str | None = None
    email: str | None = None
    webhook_url: HttpUrl | None = None
    logo: str | None = None
    viewer: bool | None = None
    admin: bool | None = None
    bot: bool | None = None
    emoji: str | None = None

    @field_validator("logo")
    @classmethod
    def validate_logo(cls, v: str | None) -> str | None:
        """Validate that logo is one of the available options."""
        if v is not None and v not in AVAILABLE_LOGOS:
            raise ValueError(f"Logo must be one of: {', '.join(AVAILABLE_LOGOS)}")
        return v

    @field_validator("emoji")
    @classmethod
    def validate_emoji(cls, v: str | None) -> str | None:
        """Validate that emoji is a single character."""
        if v is not None and len(v) > 10:  # Allow up to 10 chars for complex emojis
            raise ValueError("Emoji must be 10 characters or less")
        return v

    @model_validator(mode="after")
    def validate_bot_cannot_have_logo(self):
        """Validate that bots cannot have logos."""
        if self.bot is True and self.logo is not None:
            raise ValueError("Bots can only use emoji for avatars, not logos")
        return self


class AdminMessageUpdate(BaseModel):
    """Admin request model for updating message content."""

    content: str = Field(..., min_length=1, max_length=10000)


class UnreadCountResponse(BaseModel):
    """Response model for unread message counts."""

    unread_room_messages: int
    unread_direct_messages: int
    total_unread: int


class AssignRoleRequest(BaseModel):
    """Request model for assigning a role to a user (admin only)."""

    role: Role


class AssignRoleResponse(BaseModel):
    """Response model for role assignment."""

    username: str
    role: Role
    message: str


class CreateBotRequest(BaseModel):
    """Request model for creating a bot."""

    username: str = Field(..., min_length=1, max_length=50)
    emoji: str | None = None
    webhook_url: HttpUrl | None = None

    @field_validator("emoji")
    @classmethod
    def validate_emoji(cls, v: str | None) -> str | None:
        """Validate that emoji is a single character."""
        if v is not None and len(v) > 10:  # Allow up to 10 chars for complex emojis
            raise ValueError("Emoji must be 10 characters or less")
        return v


class CreateBotResponse(BaseModel):
    """Response model for bot creation."""

    id: str  # Bot UUID as string
    username: str
    api_key: str
    created_by_id: str  # Creator UUID as string
    created_by: str  # Creator username (deprecated, use created_by_id)
    emoji: str | None = None
    webhook_url: HttpUrl | None = None


class BotProfileResponse(BaseModel):
    """Response model for bot profile."""

    id: str  # Bot UUID as string
    username: str
    api_key: str
    created_by_id: str  # Creator UUID as string
    created_by: str  # Creator username (deprecated, use created_by_id)
    emoji: str | None = None
    webhook_url: HttpUrl | None = None
    created_at: str


class UpdateBotRequest(BaseModel):
    """Request model for updating a bot."""

    emoji: str | None = None
    webhook_url: HttpUrl | None = None

    @field_validator("emoji")
    @classmethod
    def validate_emoji(cls, v: str | None) -> str | None:
        """Validate that emoji is a single character."""
        if v is not None and len(v) > 10:  # Allow up to 10 chars for complex emojis
            raise ValueError("Emoji must be 10 characters or less")
        return v


class InviteUserRequest(BaseModel):
    """Request to invite a user by email."""

    email: str = Field(..., description="Email address to invite")
    role: Role = Field(default=Role.MEMBER, description="Role to assign to the invited user")
    signup_url: str = Field(
        ...,
        description="URL to redirect to after clicking magic link (e.g., https://app.example.com/signup)",
    )


class InviteUserResponse(BaseModel):
    """Response after sending invitation."""

    email: str
    role: Role
    message: str
