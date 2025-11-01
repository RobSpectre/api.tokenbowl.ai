"""REST API endpoints for the chat server."""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from .auth import generate_api_key, get_current_admin, get_current_user, require_permission
from .config import settings
from .models import (
    AVAILABLE_LOGOS,
    AdminMessageUpdate,
    AdminUpdateUserRequest,
    AssignRoleRequest,
    AssignRoleResponse,
    BotProfileResponse,
    Conversation,
    ConversationResponse,
    CreateBotRequest,
    CreateBotResponse,
    CreateConversationRequest,
    InviteUserRequest,
    InviteUserResponse,
    Message,
    MessageResponse,
    MessageType,
    PaginatedConversationsResponse,
    PaginatedMessagesResponse,
    PaginationMetadata,
    Permission,
    PublicUserProfile,
    Role,
    SendMessageRequest,
    StytchAuthenticateRequest,
    StytchAuthenticateResponse,
    StytchLoginRequest,
    StytchLoginResponse,
    UnreadCountResponse,
    UpdateBotRequest,
    UpdateConversationRequest,
    UpdateLogoRequest,
    UpdateUsernameRequest,
    UpdateWebhookRequest,
    User,
    UserProfileResponse,
    UserRegistration,
    UserRegistrationResponse,
)
from .storage import storage
from .stytch_client import stytch_client
from .webhook import webhook_delivery
from .websocket import connection_manager, websocket_auth
from .websocket_heartbeat import heartbeat_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/register", response_model=UserRegistrationResponse, status_code=status.HTTP_201_CREATED
)
async def register_user(registration: UserRegistration) -> UserRegistrationResponse:
    """Register a new user and get an API key.

    Args:
        registration: User registration data

    Returns:
        User registration response with API key

    Raises:
        HTTPException: If username already exists
    """
    # Check if username already exists
    if storage.get_user_by_username(registration.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username {registration.username} already exists",
        )

    # Generate API key
    api_key = generate_api_key()

    # Determine role from registration data
    role = registration.get_role()

    # Prevent bot creation via /register - bots must be created via /bots endpoint
    if role == Role.BOT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bots cannot be created via /register. Please use POST /bots to create bots.",
        )

    # Create user
    # Note: Don't pass legacy boolean fields (viewer, admin, bot) here.
    # The User model's sync_role_with_legacy_fields validator will set them
    # based on the role we determined from registration.get_role()
    user = User(
        username=registration.username,
        api_key=api_key,
        webhook_url=registration.webhook_url,
        logo=registration.logo,
        role=role,
        emoji=registration.emoji,
    )

    try:
        storage.add_user(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e

    logger.info(f"Registered new user {user.username} with role {role.value}")

    return UserRegistrationResponse(
        id=str(user.id),
        username=user.username,
        api_key=api_key,
        role=role,
        webhook_url=user.webhook_url,
        logo=user.logo,
        viewer=user.viewer,
        admin=user.admin,
        bot=user.bot,
        emoji=user.emoji,
    )


@router.post("/auth/magic-link/send", response_model=StytchLoginResponse)
async def send_magic_link(request: StytchLoginRequest) -> StytchLoginResponse:
    """Send a magic link to user's email for passwordless authentication.

    If the email is new, a username must be provided to create an account.
    If the email exists, the username field is ignored.

    Args:
        request: Email and optional username

    Returns:
        Success message with email

    Raises:
        HTTPException: If Stytch is not enabled or request fails
    """
    if not stytch_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stytch authentication is not configured",
        )

    try:
        # Use configured frontend URL for magic link redirect
        magic_link_url = f"{settings.frontend_url}/auth/callback"

        await stytch_client.send_magic_link(
            email=request.email, signup_magic_link_url=magic_link_url
        )

        return StytchLoginResponse(
            message="Magic link sent! Check your email to continue.",
            email=request.email,
        )
    except Exception as e:
        logger.error(f"Failed to send magic link: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send magic link",
        ) from e


@router.post("/auth/magic-link/authenticate", response_model=StytchAuthenticateResponse)
async def authenticate_magic_link(
    request: StytchAuthenticateRequest,
) -> StytchAuthenticateResponse:
    """Authenticate a magic link token and return session information.

    If this is a new user (first time authenticating), creates a user account.
    Returns a session token for future requests and an API key.

    Args:
        request: Magic link token from email

    Returns:
        User information, session token, and API key

    Raises:
        HTTPException: If authentication fails
    """
    if not stytch_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stytch authentication is not configured",
        )

    try:
        # Authenticate with Stytch
        stytch_user_id, email, session_token = await stytch_client.authenticate_magic_link(
            request.token
        )

        # Check if user already exists
        user = storage.get_user_by_stytch_id(stytch_user_id)

        if not user:
            # Create new user - use email prefix as default username
            username = email.split("@")[0]

            # Ensure username is unique by appending numbers if needed
            base_username = username
            counter = 1
            while storage.get_user_by_username(username):
                username = f"{base_username}{counter}"
                counter += 1

            # Generate API key for programmatic access
            api_key = generate_api_key()

            # Create user
            user = User(
                username=username,
                api_key=api_key,
                stytch_user_id=stytch_user_id,
                email=email,
            )

            storage.add_user(user)
            logger.info(f"Created new user via Stytch: {user.username}")

        return StytchAuthenticateResponse(
            username=user.username,
            session_token=session_token,
            api_key=user.api_key,
        )

    except Exception as e:
        logger.error(f"Failed to authenticate magic link: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired magic link token",
        ) from e


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    message_request: SendMessageRequest,
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """Send a message to the room or as a direct message.

    Args:
        message_request: Message content and optional recipient
        current_user: Authenticated user

    Returns:
        Created message

    Raises:
        HTTPException: If recipient doesn't exist
    """
    # Determine message type
    message_type = MessageType.DIRECT if message_request.to_username else MessageType.ROOM

    # Check permissions for message type
    if message_type == MessageType.ROOM:
        if not current_user.has_permission(Permission.SEND_ROOM_MESSAGE):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role '{current_user.role.value}' does not have permission to send room messages",
            )
    else:
        if not current_user.has_permission(Permission.SEND_DIRECT_MESSAGE):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role '{current_user.role.value}' does not have permission to send direct messages",
            )

    # Validate recipient if direct message
    recipient = None
    if message_request.to_username:
        recipient = storage.get_user_by_username(message_request.to_username)
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {message_request.to_username} not found",
            )
        if recipient.viewer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot send messages to viewer user {message_request.to_username}",
            )

    # Create message
    message = Message(
        from_username=current_user.username,
        to_username=message_request.to_username,
        content=message_request.content,
        message_type=message_type,
    )

    # Store message
    storage.add_message(message)

    logger.info(
        f"Message from {current_user.username} to "
        f"{'room' if not message_request.to_username else message_request.to_username}"
    )

    # Deliver message via WebSocket and webhooks
    if message_type == MessageType.ROOM:
        # Broadcast to all users except sender via old WebSocket
        await connection_manager.broadcast_to_room(message, exclude_username=current_user.username)

        # Publish to Centrifugo if enabled
        if settings.enable_centrifugo:
            from .centrifugo_client import get_centrifugo_client

            centrifugo = get_centrifugo_client()
            await centrifugo.publish_room_message(message, current_user)

        # Send via webhooks to all chat users who have webhook URLs configured
        # Viewers are excluded as they cannot receive direct messages
        chat_users = storage.get_chat_users()
        webhook_users = [
            user
            for user in chat_users
            if user.webhook_url and user.username != current_user.username
        ]
        await webhook_delivery.broadcast_to_webhooks(message, webhook_users)

    else:
        # Direct message - recipient was already fetched above for validation
        if recipient:
            # Send via old WebSocket if connected
            await connection_manager.send_message(recipient.username, message)

            # Publish to Centrifugo if enabled
            if settings.enable_centrifugo:
                from .centrifugo_client import get_centrifugo_client

                centrifugo = get_centrifugo_client()
                await centrifugo.publish_direct_message(message, current_user, recipient)

            # Always send via webhook if configured
            if recipient.webhook_url:
                await webhook_delivery.deliver_message(recipient, message)

    return MessageResponse.from_message(message, from_user=current_user, to_user=recipient)


@router.get("/messages", response_model=PaginatedMessagesResponse)
async def get_messages(
    limit: int = 50,
    offset: int = 0,
    since: str | None = None,
    _current_user: User = Depends(get_current_user),
) -> PaginatedMessagesResponse:
    """Get recent room messages with pagination.

    Args:
        limit: Maximum number of messages to return (default: 50)
        offset: Number of messages to skip (default: 0)
        since: ISO timestamp to get messages after
        current_user: Authenticated user

    Returns:
        Paginated list of recent messages with metadata

    Raises:
        HTTPException: If since timestamp is invalid
    """
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid timestamp format. Use ISO 8601 format.",
            ) from e

    # Get total count for pagination
    total = storage.get_room_messages_count(since=since_dt)

    # Get messages with pagination
    messages = storage.get_recent_messages(limit=limit, offset=offset, since=since_dt)

    # Calculate if there are more messages
    has_more = (offset + len(messages)) < total

    # Fetch user info for all message senders and recipients
    user_cache = {}
    message_responses = []
    for msg in messages:
        if msg.from_username not in user_cache:
            user_cache[msg.from_username] = storage.get_user_by_username(msg.from_username)

        # Fetch recipient user for direct messages
        to_user = None
        if msg.to_username:
            if msg.to_username not in user_cache:
                user_cache[msg.to_username] = storage.get_user_by_username(msg.to_username)
            to_user = user_cache[msg.to_username]

        message_responses.append(
            MessageResponse.from_message(
                msg, from_user=user_cache[msg.from_username], to_user=to_user
            )
        )

    return PaginatedMessagesResponse(
        messages=message_responses,
        pagination=PaginationMetadata(
            total=total,
            offset=offset,
            limit=limit,
            has_more=has_more,
        ),
    )


@router.get("/messages/direct", response_model=PaginatedMessagesResponse)
async def get_direct_messages(
    limit: int = 50,
    offset: int = 0,
    since: str | None = None,
    current_user: User = Depends(get_current_user),
) -> PaginatedMessagesResponse:
    """Get direct messages for the current user with pagination.

    For viewer users, this returns ALL direct messages in the system.
    For regular users, this returns only their own direct messages.

    Args:
        limit: Maximum number of messages to return (default: 50)
        offset: Number of messages to skip (default: 0)
        since: ISO timestamp to get messages after
        current_user: Authenticated user

    Returns:
        Paginated list of direct messages with metadata

    Raises:
        HTTPException: If since timestamp is invalid
    """
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid timestamp format. Use ISO 8601 format.",
            ) from e

    # Viewers see ALL direct messages, regular users see only their own
    is_viewer = current_user.viewer

    # Get total count for pagination
    total = storage.get_direct_messages_count(
        current_user.username, since=since_dt, is_viewer=is_viewer
    )

    # Get messages with pagination
    messages = storage.get_direct_messages(
        current_user.username, limit=limit, offset=offset, since=since_dt, is_viewer=is_viewer
    )

    # Calculate if there are more messages
    has_more = (offset + len(messages)) < total

    # Fetch user info for all message senders and recipients
    user_cache = {}
    message_responses = []
    for msg in messages:
        if msg.from_username not in user_cache:
            user_cache[msg.from_username] = storage.get_user_by_username(msg.from_username)

        # Fetch recipient user for direct messages
        to_user = None
        if msg.to_username:
            if msg.to_username not in user_cache:
                user_cache[msg.to_username] = storage.get_user_by_username(msg.to_username)
            to_user = user_cache[msg.to_username]

        message_responses.append(
            MessageResponse.from_message(
                msg, from_user=user_cache[msg.from_username], to_user=to_user
            )
        )

    return PaginatedMessagesResponse(
        messages=message_responses,
        pagination=PaginationMetadata(
            total=total,
            offset=offset,
            limit=limit,
            has_more=has_more,
        ),
    )


@router.get("/messages/unread", response_model=list[MessageResponse])
async def get_unread_room_messages(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    """Get unread room messages for the current user.

    Args:
        limit: Maximum number of messages to return (default: 50)
        offset: Number of messages to skip (default: 0)
        current_user: Authenticated user

    Returns:
        List of unread room messages
    """
    messages = storage.get_unread_room_messages(current_user.username, limit=limit, offset=offset)

    # Fetch user info for all message senders and recipients
    user_cache = {}
    message_responses = []
    for msg in messages:
        if msg.from_username not in user_cache:
            user_cache[msg.from_username] = storage.get_user_by_username(msg.from_username)

        # Fetch recipient user for direct messages
        to_user = None
        if msg.to_username:
            if msg.to_username not in user_cache:
                user_cache[msg.to_username] = storage.get_user_by_username(msg.to_username)
            to_user = user_cache[msg.to_username]

        message_responses.append(
            MessageResponse.from_message(
                msg, from_user=user_cache[msg.from_username], to_user=to_user
            )
        )

    return message_responses


@router.get("/messages/direct/unread", response_model=list[MessageResponse])
async def get_unread_direct_messages(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    """Get unread direct messages for the current user.

    Args:
        limit: Maximum number of messages to return (default: 50)
        offset: Number of messages to skip (default: 0)
        current_user: Authenticated user

    Returns:
        List of unread direct messages
    """
    messages = storage.get_unread_direct_messages(current_user.username, limit=limit, offset=offset)

    # Fetch user info for all message senders and recipients
    user_cache = {}
    message_responses = []
    for msg in messages:
        if msg.from_username not in user_cache:
            user_cache[msg.from_username] = storage.get_user_by_username(msg.from_username)

        # Fetch recipient user for direct messages
        to_user = None
        if msg.to_username:
            if msg.to_username not in user_cache:
                user_cache[msg.to_username] = storage.get_user_by_username(msg.to_username)
            to_user = user_cache[msg.to_username]

        message_responses.append(
            MessageResponse.from_message(
                msg, from_user=user_cache[msg.from_username], to_user=to_user
            )
        )

    return message_responses


@router.get("/messages/unread/count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
) -> UnreadCountResponse:
    """Get count of unread messages for the current user.

    Args:
        current_user: Authenticated user

    Returns:
        Count of unread room messages, direct messages, and total
    """
    unread_room, unread_direct, total_unread = storage.get_unread_count(current_user.username)
    return UnreadCountResponse(
        unread_room_messages=unread_room,
        unread_direct_messages=unread_direct,
        total_unread=total_unread,
    )


@router.post("/messages/{message_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_message_as_read(
    message_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Mark a message as read.

    Args:
        message_id: ID of the message to mark as read
        current_user: Authenticated user

    Raises:
        HTTPException: If message doesn't exist
    """
    # Verify message exists
    message = storage.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )

    storage.mark_message_as_read(message_id, current_user.username)
    logger.info(f"User {current_user.username} marked message {message_id} as read")


@router.post("/messages/mark-all-read", response_model=dict[str, int])
async def mark_all_messages_as_read(
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Mark all messages as read for the current user.

    Args:
        current_user: Authenticated user

    Returns:
        Number of messages marked as read
    """
    count = storage.mark_all_messages_as_read(current_user.username)
    logger.info(f"User {current_user.username} marked {count} messages as read")
    return {"marked_as_read": count}


@router.get("/users", response_model=list[PublicUserProfile])
async def get_users(_current_user: User = Depends(get_current_user)) -> list[PublicUserProfile]:
    """Get list of all chat users (non-viewer users) with their display info.

    Viewer users are excluded from this list as they cannot receive messages.

    Args:
        current_user: Authenticated user

    Returns:
        List of chat user profiles with logos, emojis, and bot status
    """
    users = storage.get_chat_users()
    return [
        PublicUserProfile(
            id=str(user.id),
            username=user.username,
            role=user.role,
            logo=user.logo,
            emoji=user.emoji,
            bot=user.bot,
            viewer=user.viewer,
        )
        for user in users
    ]


@router.get("/users/online", response_model=list[PublicUserProfile])
async def get_online_users(
    _current_user: User = Depends(get_current_user),
) -> list[PublicUserProfile]:
    """Get list of users currently connected via WebSocket with their display info.

    Args:
        current_user: Authenticated user

    Returns:
        List of online user profiles with logos, emojis, and bot status
    """
    online_usernames = connection_manager.get_connected_users()
    online_users = []
    for username in online_usernames:
        user = storage.get_user_by_username(username)
        if user:
            online_users.append(
                PublicUserProfile(
                    id=str(user.id),
                    username=user.username,
                    role=user.role,
                    logo=user.logo,
                    emoji=user.emoji,
                    bot=user.bot,
                    viewer=user.viewer,
                )
            )
    return online_users


@router.get("/logos", response_model=list[str])
async def get_available_logos() -> list[str]:
    """Get list of available logo filenames.

    This is a public endpoint - no authentication required.

    Returns:
        List of available logo filenames
    """
    return AVAILABLE_LOGOS


@router.patch("/users/me/logo", response_model=dict[str, str])
async def update_my_logo(
    request: UpdateLogoRequest,
    current_user: User = Depends(require_permission(Permission.UPDATE_OWN_PROFILE)),
) -> dict[str, str]:
    """Update the current user's logo.

    Args:
        request: Logo update request
        current_user: Authenticated user

    Returns:
        Success message with updated logo

    Raises:
        HTTPException: If logo is invalid or user not found
    """
    # Update logo
    success = storage.update_user_logo(current_user.username, request.logo)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    logger.info(f"Updated logo for user {current_user.username} to {request.logo}")

    return {"message": "Logo updated successfully", "logo": request.logo or ""}


@router.patch("/users/me/webhook", response_model=dict[str, str])
async def update_my_webhook(
    request: UpdateWebhookRequest,
    current_user: User = Depends(require_permission(Permission.UPDATE_OWN_PROFILE)),
) -> dict[str, str]:
    """Update the current user's webhook URL.

    Args:
        request: Webhook URL update request
        current_user: Authenticated user

    Returns:
        Success message with updated webhook URL

    Raises:
        HTTPException: If user not found
    """
    # Update webhook URL
    webhook_str = str(request.webhook_url) if request.webhook_url else None
    success = storage.update_user_webhook(current_user.id, webhook_str)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    logger.info(f"Updated webhook URL for user {current_user.username}")

    return {
        "message": "Webhook URL updated successfully",
        "webhook_url": webhook_str or "",
    }


@router.get("/users/me", response_model=UserProfileResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)) -> UserProfileResponse:
    """Get the current user's profile information.

    Args:
        current_user: Authenticated user

    Returns:
        User profile with email, API key, and other information
    """
    return UserProfileResponse(
        id=str(current_user.id),
        username=current_user.username,
        role=current_user.role,
        email=current_user.email,
        api_key=current_user.api_key,
        webhook_url=current_user.webhook_url,
        logo=current_user.logo,
        viewer=current_user.viewer,
        admin=current_user.admin,
        bot=current_user.bot,
        emoji=current_user.emoji,
        created_at=current_user.created_at.isoformat(),
    )


@router.patch("/users/me/username", response_model=UserProfileResponse)
async def update_my_username(
    request: UpdateUsernameRequest,
    current_user: User = Depends(require_permission(Permission.UPDATE_OWN_PROFILE)),
) -> UserProfileResponse:
    """Update the current user's username.

    Args:
        request: New username
        current_user: Authenticated user

    Returns:
        Updated user profile

    Raises:
        HTTPException: If username already exists or update fails
    """
    try:
        storage.update_username(current_user.username, request.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e

    # Fetch updated user
    updated_user = storage.get_user_by_username(request.username)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated user",
        )

    logger.info(f"Updated username from {current_user.username} to {request.username}")

    return UserProfileResponse(
        id=str(updated_user.id),
        username=updated_user.username,
        role=updated_user.role,
        email=updated_user.email,
        api_key=updated_user.api_key,
        webhook_url=updated_user.webhook_url,
        logo=updated_user.logo,
        viewer=updated_user.viewer,
        admin=updated_user.admin,
        bot=updated_user.bot,
        emoji=updated_user.emoji,
        created_at=updated_user.created_at.isoformat(),
    )


@router.post("/users/me/regenerate-api-key", response_model=dict[str, str])
async def regenerate_my_api_key(
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Regenerate the current user's API key.

    This generates a new API key and invalidates the old one.
    The old API key will no longer work for authentication.

    Args:
        current_user: Authenticated user

    Returns:
        Success message with new API key

    Raises:
        HTTPException: If user not found
    """
    # Generate new API key
    new_api_key = generate_api_key()

    # Update API key in storage
    success = storage.update_user_api_key(current_user.id, new_api_key)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    logger.info(f"Regenerated API key for user {current_user.username}")

    return {
        "message": "API key regenerated successfully",
        "api_key": new_api_key,
    }


@router.get("/users/{user_id}", response_model=PublicUserProfile)
async def get_user_profile(
    user_id: str,
    _current_user: User = Depends(get_current_user),
) -> PublicUserProfile:
    """Get public profile for a specific user.

    Returns public information (username, logo, emoji, bot, viewer status)
    without sensitive data (API key, email, webhook URL).

    Args:
        user_id: User UUID to retrieve
        current_user: Authenticated user

    Returns:
        Public user profile

    Raises:
        HTTPException: If user not found or invalid UUID
    """
    try:
        user_uuid = UUID(user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user ID format: {user_id}",
        ) from e

    user = storage.get_user_by_id(user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    return PublicUserProfile(
        id=str(user.id),
        username=user.username,
        role=user.role,
        logo=user.logo,
        emoji=user.emoji,
        bot=user.bot,
        viewer=user.viewer,
    )


@router.get("/admin/users", response_model=list[UserProfileResponse])
async def admin_get_all_users(
    _admin_user: User = Depends(get_current_admin),
) -> list[UserProfileResponse]:
    """Admin: Get all users with full profile information.

    Args:
        admin_user: Authenticated admin user

    Returns:
        List of all user profiles
    """
    users = storage.get_all_users()
    return [
        UserProfileResponse(
            id=str(user.id),
            username=user.username,
            role=user.role,
            email=user.email,
            api_key=user.api_key,
            webhook_url=user.webhook_url,
            logo=user.logo,
            viewer=user.viewer,
            admin=user.admin,
            bot=user.bot,
            emoji=user.emoji,
            created_at=user.created_at.isoformat(),
        )
        for user in users
    ]


@router.get("/admin/users/{user_id}", response_model=UserProfileResponse)
async def admin_get_user(
    user_id: str,
    _admin_user: User = Depends(get_current_admin),
) -> UserProfileResponse:
    """Admin: Get a specific user's full profile.

    Args:
        user_id: User UUID to retrieve
        admin_user: Authenticated admin user

    Returns:
        User profile

    Raises:
        HTTPException: If user not found or invalid UUID
    """
    try:
        user_uuid = UUID(user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user ID format: {user_id}",
        ) from e

    user = storage.get_user_by_id(user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    return UserProfileResponse(
        id=str(user.id),
        username=user.username,
        role=user.role,
        email=user.email,
        api_key=user.api_key,
        webhook_url=user.webhook_url,
        logo=user.logo,
        viewer=user.viewer,
        admin=user.admin,
        bot=user.bot,
        emoji=user.emoji,
        created_at=user.created_at.isoformat(),
    )


@router.patch("/admin/users/{user_id}", response_model=UserProfileResponse)
async def admin_update_user(
    user_id: str,
    update_request: AdminUpdateUserRequest,
    admin_user: User = Depends(get_current_admin),
) -> UserProfileResponse:
    """Admin: Update any user's profile fields.

    Args:
        user_id: User UUID to update
        update_request: Fields to update
        admin_user: Authenticated admin user

    Returns:
        Updated user profile

    Raises:
        HTTPException: If user not found or invalid UUID
    """
    try:
        user_uuid = UUID(user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user ID format: {user_id}",
        ) from e

    # First check if user exists
    user = storage.get_user_by_id(user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Check if at least one field is being updated
    has_updates = any(
        [
            update_request.username is not None,
            update_request.email is not None,
            update_request.webhook_url is not None,
            update_request.logo is not None,
            update_request.viewer is not None,
            update_request.admin is not None,
            update_request.bot is not None,
            update_request.emoji is not None,
        ]
    )

    if not has_updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields provided to update. Valid fields: username, email, webhook_url, logo, viewer, admin, bot, emoji",
        )

    # Determine logo value - if setting bot=true and user has a logo, we must clear it
    # We need to explicitly pass a value to update, not None (which means "don't update")
    logo_to_update = update_request.logo
    if update_request.bot is True and user.logo and update_request.logo is None:
        # User has a logo and we're setting bot=true, so we must clear the logo
        # Pass an empty string which we'll convert to None in storage
        logo_to_update = ""
        logger.info(f"Cleared logo for {user.username} when setting bot=true")

    # Update user
    try:
        success = storage.admin_update_user(
            user_id=user_uuid,
            username=update_request.username,
            email=update_request.email,
            webhook_url=str(update_request.webhook_url) if update_request.webhook_url else None,
            logo=logo_to_update,  # Empty string will be converted to None in storage
            viewer=update_request.viewer,
            admin=update_request.admin,
            bot=update_request.bot,
            emoji=update_request.emoji,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user",
        )

    # Fetch updated user
    updated_user = storage.get_user_by_id(user_uuid)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated user",
        )

    logger.info(f"Admin {admin_user.username} updated user {updated_user.username}")

    return UserProfileResponse(
        id=str(updated_user.id),
        username=updated_user.username,
        role=updated_user.role,
        email=updated_user.email,
        api_key=updated_user.api_key,
        webhook_url=updated_user.webhook_url,
        logo=updated_user.logo,
        viewer=updated_user.viewer,
        admin=updated_user.admin,
        bot=updated_user.bot,
        emoji=updated_user.emoji,
        created_at=updated_user.created_at.isoformat(),
    )


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: str,
    admin_user: User = Depends(get_current_admin),
) -> None:
    """Admin: Delete a user.

    Args:
        user_id: User UUID to delete
        admin_user: Authenticated admin user

    Raises:
        HTTPException: If user not found or invalid UUID
    """
    try:
        user_uuid = UUID(user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user ID format: {user_id}",
        ) from e

    # Get user first to log username
    user = storage.get_user_by_id(user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    success = storage.delete_user(user_uuid)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user",
        )

    logger.info(f"Admin {admin_user.username} deleted user {user.username}")


@router.get("/admin/messages/{message_id}", response_model=MessageResponse)
async def admin_get_message(
    message_id: str,
    _admin_user: User = Depends(get_current_admin),
) -> MessageResponse:
    """Admin: Get a specific message by ID.

    Args:
        message_id: Message ID to retrieve
        admin_user: Authenticated admin user

    Returns:
        Message details

    Raises:
        HTTPException: If message not found
    """
    message = storage.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )

    # Fetch sender and recipient user info
    from_user = storage.get_user_by_username(message.from_username)
    to_user = storage.get_user_by_username(message.to_username) if message.to_username else None
    return MessageResponse.from_message(message, from_user=from_user, to_user=to_user)


@router.patch("/admin/messages/{message_id}", response_model=MessageResponse)
async def admin_update_message(
    message_id: str,
    update_request: AdminMessageUpdate,
    admin_user: User = Depends(get_current_admin),
) -> MessageResponse:
    """Admin: Update message content.

    Args:
        message_id: Message ID to update
        update_request: New content
        admin_user: Authenticated admin user

    Returns:
        Updated message

    Raises:
        HTTPException: If message not found
    """
    success = storage.update_message_content(message_id, update_request.content)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )

    # Fetch updated message
    message = storage.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated message",
        )

    logger.info(f"Admin {admin_user.username} updated message {message_id}")

    # Fetch sender and recipient user info
    from_user = storage.get_user_by_username(message.from_username)
    to_user = storage.get_user_by_username(message.to_username) if message.to_username else None
    return MessageResponse.from_message(message, from_user=from_user, to_user=to_user)


@router.delete("/admin/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_message(
    message_id: str,
    admin_user: User = Depends(get_current_admin),
) -> None:
    """Admin: Delete a message.

    Args:
        message_id: Message ID to delete
        admin_user: Authenticated admin user

    Raises:
        HTTPException: If message not found
    """
    success = storage.delete_message(message_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )

    logger.info(f"Admin {admin_user.username} deleted message {message_id}")


@router.delete("/admin/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_conversation(
    conversation_id: str,
    admin_user: User = Depends(get_current_admin),
) -> None:
    """Admin: Delete any conversation.

    Args:
        conversation_id: Conversation UUID to delete
        admin_user: Authenticated admin user

    Raises:
        HTTPException: If conversation not found
    """
    conversation = storage.get_conversation_by_id(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    success = storage.delete_conversation(conversation_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation",
        )

    logger.info(
        f"Admin {admin_user.username} deleted conversation {conversation_id} "
        f"(created by {conversation.created_by_username})"
    )


@router.post("/bots", response_model=CreateBotResponse, status_code=status.HTTP_201_CREATED)
async def create_bot(
    request: CreateBotRequest,
    current_user: User = Depends(require_permission(Permission.CREATE_BOT)),
) -> CreateBotResponse:
    """Create a new bot (members and admins only).

    Args:
        request: Bot creation request
        current_user: Authenticated user creating the bot

    Returns:
        Created bot information with API key

    Raises:
        HTTPException: If username already exists
    """
    # Check if username already exists
    if storage.get_user_by_username(request.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username {request.username} already exists",
        )

    # Generate API key for bot
    api_key = generate_api_key()

    # Create bot user
    bot = User(
        username=request.username,
        api_key=api_key,
        role=Role.BOT,
        created_by=current_user.id,
        emoji=request.emoji,
        webhook_url=request.webhook_url,
    )

    try:
        storage.add_user(bot)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e

    logger.info(f"User {current_user.username} created bot {bot.username}")

    return CreateBotResponse(
        id=str(bot.id),
        username=bot.username,
        api_key=api_key,
        created_by_id=str(current_user.id),
        created_by=current_user.username,
        emoji=bot.emoji,
        webhook_url=bot.webhook_url,
    )


@router.get("/bots/me", response_model=list[BotProfileResponse])
async def get_my_bots(
    current_user: User = Depends(get_current_user),
) -> list[BotProfileResponse]:
    """Get all bots created by the current user.

    Args:
        current_user: Authenticated user

    Returns:
        List of bots created by this user
    """
    bots = storage.get_bots_by_creator(current_user.username)

    bot_responses = []
    for bot in bots:
        # Look up creator username from UUID
        creator_username = ""
        if bot.created_by:
            creator = storage.get_user_by_id(bot.created_by)
            creator_username = creator.username if creator else str(bot.created_by)

        bot_responses.append(
            BotProfileResponse(
                id=str(bot.id),
                username=bot.username,
                api_key=bot.api_key,
                created_by_id=str(bot.created_by) if bot.created_by else "",
                created_by=creator_username,
                emoji=bot.emoji,
                webhook_url=bot.webhook_url,
                created_at=bot.created_at.isoformat(),
            )
        )

    return bot_responses


@router.patch("/bots/{bot_id}", response_model=BotProfileResponse)
async def update_bot(
    bot_id: str,
    request: UpdateBotRequest,
    current_user: User = Depends(get_current_user),
) -> BotProfileResponse:
    """Update a bot's configuration (owner or admin only).

    Args:
        bot_id: Bot UUID to update
        request: Update request
        current_user: Authenticated user

    Returns:
        Updated bot profile

    Raises:
        HTTPException: If bot not found, invalid UUID, or user doesn't own it
    """
    try:
        bot_uuid = UUID(bot_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bot ID format: {bot_id}",
        ) from e

    # Get the bot
    bot = storage.get_user_by_id(bot_uuid)
    if not bot or bot.role != Role.BOT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bot {bot_id} not found",
        )

    # Check ownership (or admin)
    is_owner = bot.created_by == current_user.id
    is_admin = current_user.has_permission(Permission.UPDATE_ANY_BOT)

    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You don't have permission to update bot {bot.username}",
        )

    # Update bot fields
    if request.emoji is not None:
        storage.admin_update_user(bot_uuid, emoji=request.emoji)

    if request.webhook_url is not None:
        webhook_str = str(request.webhook_url) if request.webhook_url else None
        storage.update_user_webhook(bot_uuid, webhook_str)

    # Fetch updated bot
    updated_bot = storage.get_user_by_id(bot_uuid)
    if not updated_bot:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated bot",
        )

    logger.info(f"User {current_user.username} updated bot {updated_bot.username}")

    # Look up creator username from UUID
    creator_username = ""
    if updated_bot.created_by:
        creator = storage.get_user_by_id(updated_bot.created_by)
        creator_username = creator.username if creator else str(updated_bot.created_by)

    return BotProfileResponse(
        id=str(updated_bot.id),
        username=updated_bot.username,
        api_key=updated_bot.api_key,
        created_by_id=str(updated_bot.created_by) if updated_bot.created_by else "",
        created_by=creator_username,
        emoji=updated_bot.emoji,
        webhook_url=updated_bot.webhook_url,
        created_at=updated_bot.created_at.isoformat(),
    )


@router.delete("/bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    bot_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a bot (owner or admin only).

    Args:
        bot_id: Bot UUID to delete
        current_user: Authenticated user

    Raises:
        HTTPException: If bot not found, invalid UUID, or user doesn't own it
    """
    try:
        bot_uuid = UUID(bot_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bot ID format: {bot_id}",
        ) from e

    # Get the bot
    bot = storage.get_user_by_id(bot_uuid)
    if not bot or bot.role != Role.BOT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bot {bot_id} not found",
        )

    # Check ownership (or admin)
    is_owner = bot.created_by == current_user.id
    is_admin = current_user.has_permission(Permission.DELETE_ANY_BOT)

    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You don't have permission to delete bot {bot.username}",
        )

    # Delete the bot
    success = storage.delete_user(bot_uuid)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete bot",
        )

    logger.info(f"User {current_user.username} deleted bot {bot.username}")


@router.post("/bots/{bot_id}/regenerate-api-key", response_model=dict[str, str])
async def regenerate_bot_api_key(
    bot_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Regenerate a bot's API key (owner or admin only).

    Args:
        bot_id: Bot UUID
        current_user: Authenticated user

    Returns:
        Success message with new API key

    Raises:
        HTTPException: If bot not found, invalid UUID, or user doesn't own it
    """
    try:
        bot_uuid = UUID(bot_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bot ID format: {bot_id}",
        ) from e

    # Get the bot
    bot = storage.get_user_by_id(bot_uuid)
    if not bot or bot.role != Role.BOT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bot {bot_id} not found",
        )

    # Check ownership (or admin)
    is_owner = bot.created_by == current_user.id
    is_admin = current_user.has_permission(Permission.UPDATE_ANY_BOT)

    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You don't have permission to regenerate API key for bot {bot.username}",
        )

    # Generate new API key
    new_api_key = generate_api_key()

    # Update API key in storage
    success = storage.update_user_api_key(bot_uuid, new_api_key)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update bot API key",
        )

    logger.info(f"User {current_user.username} regenerated API key for bot {bot.username}")

    return {
        "message": "Bot API key regenerated successfully",
        "api_key": new_api_key,
    }


@router.patch("/admin/users/{user_id}/role", response_model=AssignRoleResponse)
async def assign_user_role(
    user_id: str,
    request: AssignRoleRequest,
    admin_user: User = Depends(require_permission(Permission.ASSIGN_ROLES)),
) -> AssignRoleResponse:
    """Admin: Assign a role to a user.

    Args:
        user_id: User UUID to assign role to
        request: Role assignment request
        admin_user: Authenticated admin user with ASSIGN_ROLES permission

    Returns:
        Role assignment response

    Raises:
        HTTPException: If user not found or invalid UUID
    """
    try:
        user_uuid = UUID(user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid user ID format: {user_id}",
        ) from e

    # Verify user exists
    user = storage.get_user_by_id(user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Update role in database
    success = storage.update_user_role(user_uuid, request.role)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user role",
        )

    # Sync role to Stytch if user has Stytch ID
    if user.stytch_user_id and stytch_client.enabled:
        try:
            await stytch_client.set_user_role(user.stytch_user_id, request.role)
            logger.info(f"Synced role {request.role.value} to Stytch for user {user.username}")
        except Exception as e:
            logger.error(f"Failed to sync role to Stytch for user {user.username}: {e}")
            # Don't fail the request if Stytch sync fails - database is source of truth

    logger.info(
        f"Admin {admin_user.username} assigned role {request.role.value} to user {user.username}"
    )

    return AssignRoleResponse(
        username=user.username,
        role=request.role,
        message=f"Successfully assigned role '{request.role.value}' to user {user.username}",
    )


@router.post("/admin/invite", response_model=InviteUserResponse)
async def invite_user_by_email(
    request: InviteUserRequest,
    admin_user: User = Depends(get_current_admin),
) -> InviteUserResponse:
    """Admin: Invite a user by email using Stytch magic link.

    Sends a magic link invitation to the specified email address. When the user clicks
    the link and authenticates, they will be automatically registered with the specified role.

    Args:
        request: Invite request with email, role, and signup URL
        admin_user: Authenticated admin user

    Returns:
        Invite response with confirmation

    Raises:
        HTTPException: If Stytch is not enabled or invitation fails
    """
    if not stytch_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email invitations are not available. Stytch is not configured.",
        )

    try:
        # Send magic link via Stytch
        await stytch_client.send_magic_link(
            email=request.email,
            signup_magic_link_url=request.signup_url,
        )

        logger.info(
            f"Admin {admin_user.username} sent invitation to {request.email} with role {request.role.value}"
        )

        return InviteUserResponse(
            email=request.email,
            role=request.role,
            message=f"Invitation sent successfully to {request.email}. User will be assigned role '{request.role.value}' upon registration.",
        )

    except Exception as e:
        logger.error(f"Failed to send invitation to {request.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send invitation: {str(e)}",
        ) from e


# Conversation endpoints


@router.post(
    "/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED
)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    """Create a new conversation.

    Args:
        request: Conversation creation request
        current_user: Authenticated user

    Returns:
        Created conversation

    Raises:
        HTTPException: If message IDs are invalid
    """
    # Convert string UUIDs to UUID objects
    message_ids = [UUID(msg_id) for msg_id in request.message_ids]

    # Verify all message IDs exist
    for msg_id in message_ids:
        message = storage.get_message_by_id(str(msg_id))
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message {msg_id} not found",
            )

    # Create conversation
    conversation = Conversation(
        title=request.title,
        description=request.description,
        message_ids=message_ids,
        created_by_username=current_user.username,
    )

    storage.add_conversation(conversation)

    logger.info(
        f"User {current_user.username} created conversation {conversation.id} with {len(message_ids)} messages"
    )

    return ConversationResponse.from_conversation(conversation)


@router.get("/conversations", response_model=PaginatedConversationsResponse)
async def get_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
) -> PaginatedConversationsResponse:
    """Get conversations created by the current user (or all conversations if viewer).

    Viewers can see all conversations from all users.
    Regular users can only see their own conversations.

    Args:
        limit: Maximum number of conversations to return
        offset: Number of conversations to skip
        current_user: Authenticated user

    Returns:
        Paginated list of conversations
    """
    # Viewers can see all conversations
    if current_user.viewer:
        conversations = storage.get_all_conversations(limit, offset)
        total = storage.get_conversations_count()
    else:
        conversations = storage.get_conversations_by_user(current_user.username, limit, offset)
        total = storage.get_conversations_count(current_user.username)

    return PaginatedConversationsResponse(
        conversations=[ConversationResponse.from_conversation(c) for c in conversations],
        pagination=PaginationMetadata(
            total=total,
            offset=offset,
            limit=limit,
            has_more=offset + len(conversations) < total,
        ),
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    """Get a specific conversation.

    Viewers can view any conversation.
    Regular users can only view their own conversations.

    Args:
        conversation_id: Conversation UUID
        current_user: Authenticated user

    Returns:
        Conversation details

    Raises:
        HTTPException: If conversation not found or user doesn't own it
    """
    conversation = storage.get_conversation_by_id(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Only the creator or viewers can view the conversation
    if not current_user.viewer and conversation.created_by_username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own conversations",
        )

    return ConversationResponse.from_conversation(conversation)


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    """Update a conversation.

    Args:
        conversation_id: Conversation UUID
        request: Update request
        current_user: Authenticated user

    Returns:
        Updated conversation

    Raises:
        HTTPException: If conversation not found, user doesn't own it, or message IDs are invalid
    """
    conversation = storage.get_conversation_by_id(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Only the creator can update their conversation
    if conversation.created_by_username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own conversations",
        )

    # Convert string UUIDs to UUID objects if provided
    message_ids = None
    if request.message_ids is not None:
        message_ids = [UUID(msg_id) for msg_id in request.message_ids]

        # Verify all message IDs exist
        for msg_id in message_ids:
            message = storage.get_message_by_id(str(msg_id))
            if not message:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Message {msg_id} not found",
                )

    # Update conversation
    success = storage.update_conversation(
        conversation_id, request.title, request.description, message_ids
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update conversation",
        )

    # Fetch updated conversation
    updated_conversation = storage.get_conversation_by_id(conversation_id)
    if not updated_conversation:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated conversation",
        )

    logger.info(f"User {current_user.username} updated conversation {conversation_id}")

    return ConversationResponse.from_conversation(updated_conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a conversation.

    Args:
        conversation_id: Conversation UUID
        current_user: Authenticated user

    Raises:
        HTTPException: If conversation not found or user doesn't own it
    """
    conversation = storage.get_conversation_by_id(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Only the creator can delete their conversation
    if conversation.created_by_username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own conversations",
        )

    success = storage.delete_conversation(conversation_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation",
        )

    logger.info(f"User {current_user.username} deleted conversation {conversation_id}")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time messaging, read receipts, and data queries.

    Connect with API key as query parameter: /ws?api_key=YOUR_API_KEY
    Or send API key in X-API-Key header

    Supported message types:

    Messaging:
    - Send message: {"type": "message", "content": "...", "to_username": "..."}
      or {"content": "...", "to_username": "..."} (backward compatible)

    Read Receipts:
    - Mark as read: {"type": "mark_read", "message_id": "..."}
    - Mark all as read: {"type": "mark_all_read"}
    - Mark room read: {"type": "mark_room_read"}
    - Mark direct read: {"type": "mark_direct_read", "from_username": "..."}
    - Get unread count: {"type": "get_unread_count"}

    Message History:
    - Get room messages: {"type": "get_messages", "limit": 50, "offset": 0, "since": "ISO-timestamp"}
    - Get direct messages: {"type": "get_direct_messages", "limit": 50, "offset": 0, "since": "ISO-timestamp"}
    - Get unread room messages: {"type": "get_unread_messages", "limit": 50, "offset": 0}
    - Get unread direct messages: {"type": "get_unread_direct_messages", "limit": 50, "offset": 0}

    User Discovery:
    - Get all users: {"type": "get_users"}
    - Get online users: {"type": "get_online_users"}
    - Get user profile: {"type": "get_user_profile", "username": "..."}

    Conversations:
    - Create conversation: {"type": "create_conversation", "title": "...", "message_ids": ["uuid1", "uuid2"]}
    - Get conversations: {"type": "get_conversations", "limit": 50, "offset": 0}
    - Get conversation: {"type": "get_conversation", "conversation_id": "..."}
    - Update conversation: {"type": "update_conversation", "conversation_id": "...", "title": "...", "message_ids": ["uuid1", "uuid2"]}
    - Delete conversation: {"type": "delete_conversation", "conversation_id": "..."}

    Administration (admins only):
    - Delete message: {"type": "delete_message", "message_id": "..."}

    Args:
        websocket: WebSocket connection
    """
    user = await websocket_auth(websocket)
    if not user:
        return

    await connection_manager.connect(websocket, user)

    try:
        while True:
            # Receive data from client
            data = await websocket.receive_json()

            # Update activity timestamp for this specific connection
            heartbeat_manager.update_activity(user.username, websocket)

            # Determine message type (default to "message" for backward compatibility)
            msg_type = data.get("type", "message")

            # Handle different message types
            if msg_type == "message":
                # Send a message
                content = data.get("content")
                to_username = data.get("to_username")

                if not content:
                    await websocket.send_json({"type": "error", "error": "Missing content field"})
                    continue

                # Validate recipient if direct message
                if to_username:
                    recipient = storage.get_user_by_username(to_username)
                    if not recipient:
                        await websocket.send_json(
                            {"type": "error", "error": f"User {to_username} not found"}
                        )
                        continue
                    if recipient.viewer:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": f"Cannot send messages to viewer user {to_username}",
                            }
                        )
                        continue

                # Create and store message
                message_type = MessageType.DIRECT if to_username else MessageType.ROOM

                # Check permissions for message type
                if message_type == MessageType.ROOM:
                    if not user.has_permission(Permission.SEND_ROOM_MESSAGE):
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": f"Your role '{user.role.value}' does not have permission to send room messages",
                            }
                        )
                        continue
                else:
                    if not user.has_permission(Permission.SEND_DIRECT_MESSAGE):
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": f"Your role '{user.role.value}' does not have permission to send direct messages",
                            }
                        )
                        continue

                message = Message(
                    from_username=user.username,
                    to_username=to_username,
                    content=content,
                    message_type=message_type,
                )
                storage.add_message(message)

                logger.info(
                    f"WebSocket message from {user.username} to "
                    f"{to_username if to_username else 'room'}"
                )

                # Deliver message
                if message_type == MessageType.ROOM:
                    # Broadcast to all users except sender via old WebSocket
                    await connection_manager.broadcast_to_room(
                        message, exclude_username=user.username
                    )

                    # Publish to Centrifugo if enabled
                    if settings.enable_centrifugo:
                        from .centrifugo_client import get_centrifugo_client

                        centrifugo = get_centrifugo_client()
                        await centrifugo.publish_room_message(message, user)

                    # Send via webhooks to all chat users who have webhook URLs configured
                    chat_users = storage.get_chat_users()
                    webhook_users = [
                        u for u in chat_users if u.webhook_url and u.username != user.username
                    ]
                    await webhook_delivery.broadcast_to_webhooks(message, webhook_users)

                else:
                    # Direct message
                    recipient = storage.get_user_by_username(to_username)
                    if recipient:
                        # Send via old WebSocket if connected
                        await connection_manager.send_message(recipient.username, message)

                        # Publish to Centrifugo if enabled
                        if settings.enable_centrifugo:
                            from .centrifugo_client import get_centrifugo_client

                            centrifugo = get_centrifugo_client()
                            await centrifugo.publish_direct_message(message, user, recipient)

                        # Always send via webhook if configured
                        if recipient.webhook_url:
                            await webhook_delivery.deliver_message(recipient, message)

                # Send confirmation back to sender
                # Fetch recipient user for direct messages
                recipient_user = storage.get_user_by_username(to_username) if to_username else None
                await websocket.send_json(
                    {
                        "type": "message_sent",
                        "status": "sent",
                        "message": MessageResponse.from_message(
                            message, from_user=user, to_user=recipient_user
                        ).model_dump(),
                    }
                )

            elif msg_type == "mark_read":
                # Mark a message as read
                message_id = data.get("message_id")

                if not message_id:
                    await websocket.send_json(
                        {"type": "error", "error": "Missing message_id field"}
                    )
                    continue

                # Verify message exists
                message_result = storage.get_message_by_id(message_id)
                if not message_result:
                    await websocket.send_json(
                        {"type": "error", "error": f"Message {message_id} not found"}
                    )
                    continue

                message = message_result  # Type narrowing: now message is guaranteed to be Message

                # Mark as read
                was_created = storage.mark_message_as_read(message_id, user.username)

                if was_created:
                    logger.info(f"User {user.username} marked message {message_id} as read")

                    # Send read receipt notification to the message sender
                    # Only send if sender is connected and sender is not the reader
                    if message.from_username != user.username:
                        await connection_manager.send_notification(
                            message.from_username,
                            {
                                "type": "read_receipt",
                                "message_id": message_id,
                                "read_by": user.username,
                            },
                        )

                # Confirm to the reader
                await websocket.send_json(
                    {"type": "marked_read", "message_id": message_id, "status": "success"}
                )

            elif msg_type == "mark_all_read":
                # Mark all messages as read
                count = storage.mark_all_messages_as_read(user.username)
                logger.info(f"User {user.username} marked {count} messages as read via WebSocket")

                await websocket.send_json(
                    {"type": "marked_all_read", "marked_as_read": count, "status": "success"}
                )

            elif msg_type == "get_unread_count":
                # Get unread count
                unread_room, unread_direct, total_unread = storage.get_unread_count(user.username)

                await websocket.send_json(
                    {
                        "type": "unread_count",
                        "unread_room_messages": unread_room,
                        "unread_direct_messages": unread_direct,
                        "total_unread": total_unread,
                    }
                )

            elif msg_type == "mark_room_read":
                # Mark all room messages as read
                unread_messages = storage.get_unread_room_messages(user.username)
                count = 0
                for msg in unread_messages:
                    storage.mark_message_as_read(str(msg.id), user.username)
                    count += 1

                logger.info(
                    f"User {user.username} marked {count} room messages as read via WebSocket"
                )

                await websocket.send_json({"status": "marked_read", "count": count})

            elif msg_type == "mark_direct_read":
                # Mark all direct messages from a specific user as read
                from_username = data.get("from_username")

                if not from_username:
                    await websocket.send_json(
                        {"type": "error", "error": "Missing from_username field"}
                    )
                    continue

                # Get all direct messages between current user and the specified user
                all_direct_messages = storage.get_direct_messages(user.username)
                count = 0
                for msg in all_direct_messages:
                    # Mark as read if it's from the specified user
                    if msg.from_username == from_username:
                        storage.mark_message_as_read(str(msg.id), user.username)
                        count += 1

                logger.info(
                    f"User {user.username} marked {count} direct messages from {from_username} as read via WebSocket"
                )

                await websocket.send_json(
                    {"status": "marked_read", "from_username": from_username, "count": count}
                )

            elif msg_type == "get_messages":
                # Get room message history with pagination
                limit = data.get("limit", 50)
                offset = data.get("offset", 0)
                since = data.get("since")

                # Parse since timestamp if provided
                since_dt = None
                if since:
                    try:
                        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    except ValueError:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": "Invalid timestamp format. Use ISO 8601 format.",
                            }
                        )
                        continue

                # Get total count for pagination
                total = storage.get_room_messages_count(since=since_dt)

                # Get messages with pagination
                messages = storage.get_recent_messages(limit=limit, offset=offset, since=since_dt)

                # Calculate if there are more messages
                has_more = (offset + len(messages)) < total

                # Fetch user info for all message senders and recipients
                user_cache = {}
                message_responses = []
                for msg in messages:
                    if msg.from_username not in user_cache:
                        user_cache[msg.from_username] = storage.get_user_by_username(
                            msg.from_username
                        )

                    # Fetch recipient user for direct messages
                    to_user = None
                    if msg.to_username:
                        if msg.to_username not in user_cache:
                            user_cache[msg.to_username] = storage.get_user_by_username(
                                msg.to_username
                            )
                        to_user = user_cache[msg.to_username]

                    message_responses.append(
                        MessageResponse.from_message(
                            msg, from_user=user_cache[msg.from_username], to_user=to_user
                        ).model_dump()
                    )

                await websocket.send_json(
                    {
                        "type": "messages",
                        "messages": message_responses,
                        "pagination": {
                            "total": total,
                            "offset": offset,
                            "limit": limit,
                            "has_more": has_more,
                        },
                    }
                )

            elif msg_type == "get_direct_messages":
                # Get direct message history with pagination
                limit = data.get("limit", 50)
                offset = data.get("offset", 0)
                since = data.get("since")

                # Parse since timestamp if provided
                since_dt = None
                if since:
                    try:
                        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    except ValueError:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": "Invalid timestamp format. Use ISO 8601 format.",
                            }
                        )
                        continue

                # Get total count for pagination
                total = storage.get_direct_messages_count(user.username, since=since_dt)

                # Get messages with pagination
                messages = storage.get_direct_messages(
                    user.username, limit=limit, offset=offset, since=since_dt
                )

                # Calculate if there are more messages
                has_more = (offset + len(messages)) < total

                # Fetch user info for all message senders and recipients
                user_cache = {}
                message_responses = []
                for msg in messages:
                    if msg.from_username not in user_cache:
                        user_cache[msg.from_username] = storage.get_user_by_username(
                            msg.from_username
                        )

                    # Fetch recipient user for direct messages
                    to_user = None
                    if msg.to_username:
                        if msg.to_username not in user_cache:
                            user_cache[msg.to_username] = storage.get_user_by_username(
                                msg.to_username
                            )
                        to_user = user_cache[msg.to_username]

                    message_responses.append(
                        MessageResponse.from_message(
                            msg, from_user=user_cache[msg.from_username], to_user=to_user
                        ).model_dump()
                    )

                await websocket.send_json(
                    {
                        "type": "direct_messages",
                        "messages": message_responses,
                        "pagination": {
                            "total": total,
                            "offset": offset,
                            "limit": limit,
                            "has_more": has_more,
                        },
                    }
                )

            elif msg_type == "get_unread_messages":
                # Get unread room messages
                limit = data.get("limit", 50)
                offset = data.get("offset", 0)

                messages = storage.get_unread_room_messages(
                    user.username, limit=limit, offset=offset
                )

                # Fetch user info for all message senders and recipients
                user_cache = {}
                message_responses = []
                for msg in messages:
                    if msg.from_username not in user_cache:
                        user_cache[msg.from_username] = storage.get_user_by_username(
                            msg.from_username
                        )

                    # Fetch recipient user for direct messages
                    to_user = None
                    if msg.to_username:
                        if msg.to_username not in user_cache:
                            user_cache[msg.to_username] = storage.get_user_by_username(
                                msg.to_username
                            )
                        to_user = user_cache[msg.to_username]

                    message_responses.append(
                        MessageResponse.from_message(
                            msg, from_user=user_cache[msg.from_username], to_user=to_user
                        ).model_dump()
                    )

                await websocket.send_json(
                    {
                        "type": "unread_messages",
                        "messages": message_responses,
                    }
                )

            elif msg_type == "get_unread_direct_messages":
                # Get unread direct messages
                limit = data.get("limit", 50)
                offset = data.get("offset", 0)

                messages = storage.get_unread_direct_messages(
                    user.username, limit=limit, offset=offset
                )

                # Fetch user info for all message senders and recipients
                user_cache = {}
                message_responses = []
                for msg in messages:
                    if msg.from_username not in user_cache:
                        user_cache[msg.from_username] = storage.get_user_by_username(
                            msg.from_username
                        )

                    # Fetch recipient user for direct messages
                    to_user = None
                    if msg.to_username:
                        if msg.to_username not in user_cache:
                            user_cache[msg.to_username] = storage.get_user_by_username(
                                msg.to_username
                            )
                        to_user = user_cache[msg.to_username]

                    message_responses.append(
                        MessageResponse.from_message(
                            msg, from_user=user_cache[msg.from_username], to_user=to_user
                        ).model_dump()
                    )

                await websocket.send_json(
                    {
                        "type": "unread_direct_messages",
                        "messages": message_responses,
                    }
                )

            elif msg_type == "get_users":
                # Get all chat users
                users = storage.get_chat_users()
                user_profiles = [
                    {
                        "username": u.username,
                        "role": u.role.value,
                        "logo": u.logo,
                        "emoji": u.emoji,
                        "bot": u.bot,
                        "viewer": u.viewer,
                    }
                    for u in users
                ]

                await websocket.send_json(
                    {
                        "type": "users",
                        "users": user_profiles,
                    }
                )

            elif msg_type == "get_online_users":
                # Get online users
                online_usernames = connection_manager.get_connected_users()
                online_users = []
                for username in online_usernames:
                    u = storage.get_user_by_username(username)
                    if u:
                        online_users.append(
                            {
                                "username": u.username,
                                "role": u.role.value,
                                "logo": u.logo,
                                "emoji": u.emoji,
                                "bot": u.bot,
                                "viewer": u.viewer,
                            }
                        )

                await websocket.send_json(
                    {
                        "type": "online_users",
                        "users": online_users,
                    }
                )

            elif msg_type == "get_user_profile":
                # Get user profile
                username = data.get("username")

                if not username:
                    await websocket.send_json({"type": "error", "error": "Missing username field"})
                    continue

                u = storage.get_user_by_username(username)
                if not u:
                    await websocket.send_json(
                        {"type": "error", "error": f"User {username} not found"}
                    )
                    continue

                await websocket.send_json(
                    {
                        "type": "user_profile",
                        "user": {
                            "username": u.username,
                            "role": u.role.value,
                            "logo": u.logo,
                            "emoji": u.emoji,
                            "bot": u.bot,
                            "viewer": u.viewer,
                        },
                    }
                )

            elif msg_type == "create_conversation":
                # Create a new conversation
                title = data.get("title")
                description = data.get("description")
                message_ids_str = data.get("message_ids", [])

                # Validate message_ids format
                try:
                    message_ids = [UUID(msg_id) for msg_id in message_ids_str]
                except ValueError:
                    await websocket.send_json(
                        {"type": "error", "error": "Invalid message ID format"}
                    )
                    continue

                # Verify all message IDs exist
                for msg_id in message_ids:
                    msg_check = storage.get_message_by_id(str(msg_id))
                    if not msg_check:
                        await websocket.send_json(
                            {"type": "error", "error": f"Message {msg_id} not found"}
                        )
                        continue

                # Create conversation
                conversation = Conversation(
                    title=title,
                    description=description,
                    message_ids=message_ids,
                    created_by_username=user.username,
                )

                storage.add_conversation(conversation)

                logger.info(
                    f"User {user.username} created conversation {conversation.id} with {len(message_ids)} messages via WebSocket"
                )

                await websocket.send_json(
                    {
                        "type": "conversation_created",
                        "conversation": ConversationResponse.from_conversation(
                            conversation
                        ).model_dump(),
                    }
                )

            elif msg_type == "get_conversations":
                # Get all conversations for current user (or all if viewer)
                limit = data.get("limit", 50)
                offset = data.get("offset", 0)

                # Viewers can see all conversations
                if user.viewer:
                    conversations = storage.get_all_conversations(limit, offset)
                    total = storage.get_conversations_count()
                else:
                    conversations = storage.get_conversations_by_user(user.username, limit, offset)
                    total = storage.get_conversations_count(user.username)

                conversation_responses = [
                    ConversationResponse.from_conversation(c).model_dump() for c in conversations
                ]

                await websocket.send_json(
                    {
                        "type": "conversations",
                        "conversations": conversation_responses,
                        "pagination": {
                            "total": total,
                            "offset": offset,
                            "limit": limit,
                            "has_more": offset + len(conversations) < total,
                        },
                    }
                )

            elif msg_type == "get_conversation":
                # Get a specific conversation
                conversation_id = data.get("conversation_id")

                if not conversation_id:
                    await websocket.send_json(
                        {"type": "error", "error": "Missing conversation_id field"}
                    )
                    continue

                conv_result = storage.get_conversation_by_id(conversation_id)

                if not conv_result:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": f"Conversation {conversation_id} not found",
                        }
                    )
                    continue

                # Only the creator or viewers can view the conversation
                if not user.viewer and conv_result.created_by_username != user.username:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": "You can only view your own conversations",
                        }
                    )
                    continue

                await websocket.send_json(
                    {
                        "type": "conversation",
                        "conversation": ConversationResponse.from_conversation(
                            conv_result
                        ).model_dump(),
                    }
                )

            elif msg_type == "update_conversation":
                # Update a conversation
                conversation_id = data.get("conversation_id")
                title = data.get("title")
                description = data.get("description")
                message_ids_str = data.get("message_ids")

                if not conversation_id:
                    await websocket.send_json(
                        {"type": "error", "error": "Missing conversation_id field"}
                    )
                    continue

                conv_to_update = storage.get_conversation_by_id(conversation_id)

                if not conv_to_update:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": f"Conversation {conversation_id} not found",
                        }
                    )
                    continue

                # Only the creator can update their conversation
                if conv_to_update.created_by_username != user.username:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": "You can only update your own conversations",
                        }
                    )
                    continue

                # Convert string UUIDs to UUID objects if provided
                message_ids = None
                if message_ids_str is not None:
                    try:
                        message_ids = [UUID(msg_id) for msg_id in message_ids_str]
                    except ValueError:
                        await websocket.send_json(
                            {"type": "error", "error": "Invalid message ID format"}
                        )
                        continue

                    # Verify all message IDs exist
                    for msg_id in message_ids:
                        msg_check = storage.get_message_by_id(str(msg_id))
                        if not msg_check:
                            await websocket.send_json(
                                {"type": "error", "error": f"Message {msg_id} not found"}
                            )
                            continue

                # Update conversation
                success = storage.update_conversation(
                    conversation_id, title, description, message_ids
                )

                if not success:
                    await websocket.send_json(
                        {"type": "error", "error": "Failed to update conversation"}
                    )
                    continue

                # Fetch updated conversation
                updated_conversation = storage.get_conversation_by_id(conversation_id)

                logger.info(
                    f"User {user.username} updated conversation {conversation_id} via WebSocket"
                )

                await websocket.send_json(
                    {
                        "type": "conversation_updated",
                        "conversation": ConversationResponse.from_conversation(
                            updated_conversation
                        ).model_dump()
                        if updated_conversation
                        else None,
                    }
                )

            elif msg_type == "delete_conversation":
                # Delete a conversation
                conversation_id = data.get("conversation_id")

                if not conversation_id:
                    await websocket.send_json(
                        {"type": "error", "error": "Missing conversation_id field"}
                    )
                    continue

                conv_to_delete = storage.get_conversation_by_id(conversation_id)

                if not conv_to_delete:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": f"Conversation {conversation_id} not found",
                        }
                    )
                    continue

                # Only the creator or admins can delete the conversation
                if not user.admin and conv_to_delete.created_by_username != user.username:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": "You can only delete your own conversations",
                        }
                    )
                    continue

                success = storage.delete_conversation(conversation_id)

                if not success:
                    await websocket.send_json(
                        {"type": "error", "error": "Failed to delete conversation"}
                    )
                    continue

                if user.admin and conv_to_delete.created_by_username != user.username:
                    logger.info(
                        f"Admin {user.username} deleted conversation {conversation_id} "
                        f"(created by {conv_to_delete.created_by_username}) via WebSocket"
                    )
                else:
                    logger.info(
                        f"User {user.username} deleted conversation {conversation_id} via WebSocket"
                    )

                await websocket.send_json(
                    {
                        "type": "conversation_deleted",
                        "conversation_id": conversation_id,
                    }
                )

            elif msg_type == "delete_message":
                # Delete a message (admins only)
                if not user.admin:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": "Only admins can delete messages",
                        }
                    )
                    continue

                message_id = data.get("message_id")

                if not message_id:
                    await websocket.send_json(
                        {"type": "error", "error": "Missing message_id field"}
                    )
                    continue

                # Check if message exists
                msg_to_delete = storage.get_message_by_id(message_id)
                if not msg_to_delete:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": f"Message {message_id} not found",
                        }
                    )
                    continue

                # Delete the message
                success = storage.delete_message(message_id)

                if not success:
                    await websocket.send_json(
                        {"type": "error", "error": "Failed to delete message"}
                    )
                    continue

                logger.info(
                    f"Admin {user.username} deleted message {message_id} "
                    f"(from {msg_to_delete.from_username}) via WebSocket"
                )

                await websocket.send_json(
                    {
                        "type": "message_deleted",
                        "message_id": message_id,
                    }
                )

            elif msg_type == "pong":
                # Handle pong response from client
                heartbeat_manager.update_pong_received(user.username, websocket)
                logger.debug(f"Received pong from {user.username}")

            else:
                await websocket.send_json(
                    {"type": "error", "error": f"Unknown message type: {msg_type}"}
                )

    except WebSocketDisconnect:
        connection_manager.disconnect(user.username, websocket)
        logger.info(f"WebSocket disconnected normally - user: {user.username}")
    except Exception as e:
        logger.error(f"WebSocket ERROR - user: {user.username}, error: {e}")
        connection_manager.disconnect(user.username, websocket)


@router.get("/centrifugo/connection-token")
async def get_centrifugo_connection_token(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get connection token for Centrifugo WebSocket.

    Returns JWT token and connection information for connecting to Centrifugo.

    Args:
        current_user: Authenticated user

    Returns:
        Connection info with token and channels

    Raises:
        HTTPException: If Centrifugo is not enabled
    """
    if not settings.enable_centrifugo:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Centrifugo is not enabled on this server",
        )

    from .centrifugo_client import get_centrifugo_client

    centrifugo = get_centrifugo_client()
    token = centrifugo.generate_connection_token(current_user)

    return {
        "token": token,
        "url": settings.centrifugo_ws_url,
        "channels": [
            f"user:{current_user.username}",  # Personal DMs
            "room:main",  # Main chat room
        ],
        "user": current_user.username,
    }


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "healthy"}


@router.get("/admin/websocket/connections", response_model=dict[str, Any])
async def get_websocket_connections(
    _admin_user: User = Depends(get_current_admin),
) -> dict[str, Any]:
    """Get WebSocket connection statistics for all connected users.

    Returns:
        Dictionary with connection statistics including all connections per user

    Raises:
        HTTPException: If user is not an admin
    """
    connected_users = connection_manager.get_connected_users()
    all_connections = []

    for username in connected_users:
        user_stats = heartbeat_manager.get_connection_stats(username)
        if user_stats:
            # user_stats is now a list of connection stats for this user
            all_connections.extend(user_stats)

    return {
        "total_users": len(connected_users),
        "total_connections": len(all_connections),
        "connections": all_connections,
    }
