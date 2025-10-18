"""REST API endpoints for the chat server."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from .auth import generate_api_key, get_current_admin, get_current_user
from .models import (
    AVAILABLE_LOGOS,
    AdminMessageUpdate,
    AdminUpdateUserRequest,
    Message,
    MessageResponse,
    MessageType,
    PaginatedMessagesResponse,
    PaginationMetadata,
    SendMessageRequest,
    StytchAuthenticateRequest,
    StytchAuthenticateResponse,
    StytchLoginRequest,
    StytchLoginResponse,
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

    # Create user
    user = User(
        username=registration.username,
        api_key=api_key,
        webhook_url=registration.webhook_url,
        logo=registration.logo,
        viewer=registration.viewer,
        admin=registration.admin,
    )

    try:
        storage.add_user(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    logger.info(f"Registered new user: {user.username}")

    return UserRegistrationResponse(
        username=user.username,
        api_key=api_key,
        webhook_url=user.webhook_url,
        logo=user.logo,
        viewer=user.viewer,
        admin=user.admin,
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
        # For now, use a placeholder URL - in production, this would be the frontend URL
        magic_link_url = "http://localhost:3000/auth/callback"

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
        )


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
        )


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

    # Validate recipient if direct message
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
        # Broadcast to all users except sender
        await connection_manager.broadcast_to_room(message, exclude_username=current_user.username)

        # Send via webhooks to chat users who aren't connected via WebSocket
        # Viewers are excluded as they cannot receive direct messages
        chat_users = storage.get_chat_users()
        webhook_users = [
            user
            for user in chat_users
            if user.webhook_url
            and user.username != current_user.username
            and not connection_manager.is_connected(user.username)
        ]
        await webhook_delivery.broadcast_to_webhooks(message, webhook_users)

    else:
        # Direct message
        recipient = storage.get_user_by_username(message_request.to_username)  # type: ignore
        if recipient:
            # Try WebSocket first
            sent_via_ws = await connection_manager.send_message(recipient.username, message)

            # If not sent via WebSocket, try webhook
            if not sent_via_ws and recipient.webhook_url:
                await webhook_delivery.deliver_message(recipient, message)

    return MessageResponse.from_message(message)


@router.get("/messages", response_model=PaginatedMessagesResponse)
async def get_messages(
    limit: int = 50,
    offset: int = 0,
    since: Optional[str] = None,
    current_user: User = Depends(get_current_user),
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
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid timestamp format. Use ISO 8601 format.",
            )

    # Get total count for pagination
    total = storage.get_room_messages_count(since=since_dt)

    # Get messages with pagination
    messages = storage.get_recent_messages(limit=limit, offset=offset, since=since_dt)

    # Calculate if there are more messages
    has_more = (offset + len(messages)) < total

    return PaginatedMessagesResponse(
        messages=[MessageResponse.from_message(msg) for msg in messages],
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
    since: Optional[str] = None,
    current_user: User = Depends(get_current_user),
) -> PaginatedMessagesResponse:
    """Get direct messages for the current user with pagination.

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
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid timestamp format. Use ISO 8601 format.",
            )

    # Get total count for pagination
    total = storage.get_direct_messages_count(current_user.username, since=since_dt)

    # Get messages with pagination
    messages = storage.get_direct_messages(
        current_user.username, limit=limit, offset=offset, since=since_dt
    )

    # Calculate if there are more messages
    has_more = (offset + len(messages)) < total

    return PaginatedMessagesResponse(
        messages=[MessageResponse.from_message(msg) for msg in messages],
        pagination=PaginationMetadata(
            total=total,
            offset=offset,
            limit=limit,
            has_more=has_more,
        ),
    )


@router.get("/users", response_model=list[str])
async def get_users(current_user: User = Depends(get_current_user)) -> list[str]:
    """Get list of all chat users (non-viewer users).

    Viewer users are excluded from this list as they cannot receive messages.

    Args:
        current_user: Authenticated user

    Returns:
        List of chat user usernames
    """
    users = storage.get_chat_users()
    return [user.username for user in users]


@router.get("/users/online", response_model=list[str])
async def get_online_users(current_user: User = Depends(get_current_user)) -> list[str]:
    """Get list of users currently connected via WebSocket.

    Args:
        current_user: Authenticated user

    Returns:
        List of online usernames
    """
    return connection_manager.get_connected_users()


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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    success = storage.update_user_webhook(current_user.username, webhook_str)
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
        username=current_user.username,
        email=current_user.email,
        api_key=current_user.api_key,
        webhook_url=current_user.webhook_url,
        logo=current_user.logo,
        viewer=current_user.viewer,
        admin=current_user.admin,
        created_at=current_user.created_at.isoformat(),
    )


@router.patch("/users/me/username", response_model=UserProfileResponse)
async def update_my_username(
    request: UpdateUsernameRequest,
    current_user: User = Depends(get_current_user),
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
        )

    # Fetch updated user
    updated_user = storage.get_user_by_username(request.username)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated user",
        )

    logger.info(f"Updated username from {current_user.username} to {request.username}")

    return UserProfileResponse(
        username=updated_user.username,
        email=updated_user.email,
        api_key=updated_user.api_key,
        webhook_url=updated_user.webhook_url,
        logo=updated_user.logo,
        viewer=updated_user.viewer,
        admin=updated_user.admin,
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
    success = storage.update_user_api_key(current_user.username, new_api_key)
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


@router.get("/admin/users", response_model=list[UserProfileResponse])
async def admin_get_all_users(admin_user: User = Depends(get_current_admin)) -> list[UserProfileResponse]:
    """Admin: Get all users with full profile information.

    Args:
        admin_user: Authenticated admin user

    Returns:
        List of all user profiles
    """
    users = storage.get_all_users()
    return [
        UserProfileResponse(
            username=user.username,
            email=user.email,
            api_key=user.api_key,
            webhook_url=user.webhook_url,
            logo=user.logo,
            viewer=user.viewer,
            admin=user.admin,
            created_at=user.created_at.isoformat(),
        )
        for user in users
    ]


@router.get("/admin/users/{username}", response_model=UserProfileResponse)
async def admin_get_user(
    username: str,
    admin_user: User = Depends(get_current_admin),
) -> UserProfileResponse:
    """Admin: Get a specific user's full profile.

    Args:
        username: Username to retrieve
        admin_user: Authenticated admin user

    Returns:
        User profile

    Raises:
        HTTPException: If user not found
    """
    user = storage.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found",
        )

    return UserProfileResponse(
        username=user.username,
        email=user.email,
        api_key=user.api_key,
        webhook_url=user.webhook_url,
        logo=user.logo,
        viewer=user.viewer,
        admin=user.admin,
        created_at=user.created_at.isoformat(),
    )


@router.patch("/admin/users/{username}", response_model=UserProfileResponse)
async def admin_update_user(
    username: str,
    update_request: AdminUpdateUserRequest,
    admin_user: User = Depends(get_current_admin),
) -> UserProfileResponse:
    """Admin: Update any user's profile fields.

    Args:
        username: Username to update
        update_request: Fields to update
        admin_user: Authenticated admin user

    Returns:
        Updated user profile

    Raises:
        HTTPException: If user not found
    """
    # Update user
    success = storage.admin_update_user(
        username=username,
        email=update_request.email,
        webhook_url=str(update_request.webhook_url) if update_request.webhook_url else None,
        logo=update_request.logo,
        viewer=update_request.viewer,
        admin=update_request.admin,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found",
        )

    # Fetch updated user
    user = storage.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated user",
        )

    logger.info(f"Admin {admin_user.username} updated user {username}")

    return UserProfileResponse(
        username=user.username,
        email=user.email,
        api_key=user.api_key,
        webhook_url=user.webhook_url,
        logo=user.logo,
        viewer=user.viewer,
        admin=user.admin,
        created_at=user.created_at.isoformat(),
    )


@router.delete("/admin/users/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    username: str,
    admin_user: User = Depends(get_current_admin),
) -> None:
    """Admin: Delete a user.

    Args:
        username: Username to delete
        admin_user: Authenticated admin user

    Raises:
        HTTPException: If user not found
    """
    success = storage.delete_user(username)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found",
        )

    logger.info(f"Admin {admin_user.username} deleted user {username}")


@router.get("/admin/messages/{message_id}", response_model=MessageResponse)
async def admin_get_message(
    message_id: str,
    admin_user: User = Depends(get_current_admin),
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

    return MessageResponse.from_message(message)


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

    return MessageResponse.from_message(message)


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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time messaging.

    Connect with API key as query parameter: /ws?api_key=YOUR_API_KEY
    Or send API key in X-API-Key header

    Once connected, you'll receive all room messages and direct messages sent to you.
    You can also send messages through this WebSocket connection.

    Args:
        websocket: WebSocket connection
    """
    user = await websocket_auth(websocket)
    if not user:
        return

    await connection_manager.connect(websocket, user)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            # Parse message data
            content = data.get("content")
            to_username = data.get("to_username")

            if not content:
                await websocket.send_json({"error": "Missing content field"})
                continue

            # Validate recipient if direct message
            if to_username:
                recipient = storage.get_user_by_username(to_username)
                if not recipient:
                    await websocket.send_json({"error": f"User {to_username} not found"})
                    continue
                if recipient.viewer:
                    await websocket.send_json(
                        {"error": f"Cannot send messages to viewer user {to_username}"}
                    )
                    continue

            # Create and store message
            message_type = MessageType.DIRECT if to_username else MessageType.ROOM
            message = Message(
                from_username=user.username,
                to_username=to_username,
                content=content,
                message_type=message_type,
            )
            storage.add_message(message)

            logger.info(
                f"WebSocket message from {user.username} to "
                f"{'room' if not to_username else to_username}"
            )

            # Deliver message
            if message_type == MessageType.ROOM:
                # Broadcast to all users except sender
                await connection_manager.broadcast_to_room(message, exclude_username=user.username)

                # Send via webhooks to chat users who aren't connected
                # Viewers are excluded as they cannot receive direct messages
                chat_users = storage.get_chat_users()
                webhook_users = [
                    u
                    for u in chat_users
                    if u.webhook_url
                    and u.username != user.username
                    and not connection_manager.is_connected(u.username)
                ]
                await webhook_delivery.broadcast_to_webhooks(message, webhook_users)

            else:
                # Direct message
                recipient = storage.get_user_by_username(to_username)  # type: ignore
                if recipient:
                    sent_via_ws = await connection_manager.send_message(recipient.username, message)

                    if not sent_via_ws and recipient.webhook_url:
                        await webhook_delivery.deliver_message(recipient, message)

            # Send confirmation back to sender
            await websocket.send_json(
                {"status": "sent", "message": MessageResponse.from_message(message).model_dump()}
            )

    except WebSocketDisconnect:
        connection_manager.disconnect(user.username)
        logger.info(f"User {user.username} disconnected from WebSocket")
    except Exception as e:
        logger.error(f"WebSocket error for user {user.username}: {e}")
        connection_manager.disconnect(user.username)


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "healthy"}
