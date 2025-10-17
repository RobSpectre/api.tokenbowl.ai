"""REST API endpoints for the chat server."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from .auth import generate_api_key, get_current_user
from .models import (
    AVAILABLE_LOGOS,
    Message,
    MessageResponse,
    MessageType,
    PaginatedMessagesResponse,
    PaginationMetadata,
    SendMessageRequest,
    UpdateLogoRequest,
    User,
    UserRegistration,
    UserRegistrationResponse,
)
from .storage import storage
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
async def get_available_logos(current_user: User = Depends(get_current_user)) -> list[str]:
    """Get list of available logo filenames.

    Args:
        current_user: Authenticated user

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
