"""Tests for Role-Based Access Control (RBAC) system."""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from token_bowl_chat_server.models import Permission, Role


def test_role_assignment_by_admin(client: TestClient, registered_user: dict, registered_admin: dict) -> None:
    """Test that admins can assign roles to users."""
    admin_headers = {"X-API-Key": registered_admin["api_key"]}

    # Assign viewer role
    response = client.patch(
        f"/admin/users/{registered_user['username']}/role",
        json={"role": "viewer"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["username"] == registered_user["username"]
    assert data["role"] == "viewer"
    assert "Successfully assigned role" in data["message"]


def test_role_assignment_by_non_admin(client: TestClient, registered_user: dict, registered_user2: dict) -> None:
    """Test that non-admins cannot assign roles."""
    headers = {"X-API-Key": registered_user["api_key"]}

    response = client.patch(
        f"/admin/users/{registered_user2['username']}/role",
        json={"role": "admin"},
        headers=headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_assign_all_roles(client: TestClient, registered_user: dict, registered_admin: dict) -> None:
    """Test assigning each role type."""
    admin_headers = {"X-API-Key": registered_admin["api_key"]}

    for role in ["admin", "member", "viewer", "bot"]:
        response = client.patch(
            f"/admin/users/{registered_user['username']}/role",
            json={"role": role},
            headers=admin_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == role


def test_member_can_create_bot(client: TestClient, registered_user: dict) -> None:
    """Test that members have CREATE_BOT permission."""
    headers = {"X-API-Key": registered_user["api_key"]}

    response = client.post(
        "/bots",
        json={"username": "member_bot", "emoji": "🤖"},
        headers=headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "member_bot"
    assert data["created_by"] == registered_user["username"]


def test_viewer_cannot_create_bot(client: TestClient) -> None:
    """Test that viewers don't have CREATE_BOT permission."""
    # Register a viewer
    viewer_response = client.post(
        "/register",
        json={"username": "viewer_user", "viewer": True},
    )
    viewer_headers = {"X-API-Key": viewer_response.json()["api_key"]}

    # Try to create a bot
    response = client.post(
        "/bots",
        json={"username": "viewer_bot", "emoji": "🤖"},
        headers=viewer_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_member_can_send_direct_messages(client: TestClient, registered_user: dict, registered_user2: dict) -> None:
    """Test that members have SEND_DIRECT_MESSAGE permission."""
    headers = {"X-API-Key": registered_user["api_key"]}

    response = client.post(
        "/messages",
        json={"content": "Hello!", "to_username": registered_user2["username"]},
        headers=headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["message_type"] == "direct"


def test_member_can_send_room_messages(client: TestClient, registered_user: dict) -> None:
    """Test that members have SEND_ROOM_MESSAGE permission."""
    headers = {"X-API-Key": registered_user["api_key"]}

    response = client.post(
        "/messages",
        json={"content": "Hello room!"},
        headers=headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["message_type"] == "room"


def test_member_can_update_own_profile(client: TestClient, registered_user: dict) -> None:
    """Test that members have UPDATE_OWN_PROFILE permission."""
    headers = {"X-API-Key": registered_user["api_key"]}

    response = client.patch(
        "/users/me/logo",
        json={"logo": "claude-color.png"},
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK


def test_member_cannot_update_any_user(client: TestClient, registered_user: dict, registered_user2: dict) -> None:
    """Test that members don't have UPDATE_ANY_USER permission."""
    headers = {"X-API-Key": registered_user["api_key"]}

    response = client.patch(
        f"/admin/users/{registered_user2['username']}",
        json={"email": "hacked@example.com"},
        headers=headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_admin_has_all_permissions(client: TestClient, registered_user: dict, registered_admin: dict) -> None:
    """Test that admins have all permissions."""
    admin_headers = {"X-API-Key": registered_admin["api_key"]}

    # Can create bot
    response = client.post(
        "/bots",
        json={"username": "admin_bot", "emoji": "👑"},
        headers=admin_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Can update any user
    response = client.patch(
        f"/admin/users/{registered_user['username']}",
        json={"email": "admin-updated@example.com"},
        headers=admin_headers,
    )
    assert response.status_code == status.HTTP_200_OK

    # Can delete user
    temp_user = client.post("/register", json={"username": "temp_user"}).json()
    response = client.delete(
        f"/admin/users/{temp_user['username']}",
        headers=admin_headers,
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_viewer_can_only_read(client: TestClient) -> None:
    """Test that viewers only have read permissions."""
    # Register a viewer
    viewer_response = client.post(
        "/register",
        json={"username": "viewer_readonly", "viewer": True},
    )
    viewer_headers = {"X-API-Key": viewer_response.json()["api_key"]}

    # Can read messages
    response = client.get("/messages", headers=viewer_headers)
    assert response.status_code == status.HTTP_200_OK

    # Can read users
    response = client.get("/users", headers=viewer_headers)
    assert response.status_code == status.HTTP_200_OK

    # Cannot send messages
    response = client.post(
        "/messages",
        json={"content": "I should not be able to send this"},
        headers=viewer_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # Cannot update profile
    response = client.patch(
        "/users/me/logo",
        json={"logo": "openai.png"},
        headers=viewer_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_bot_permissions(client: TestClient, registered_user: dict) -> None:
    """Test that bots have correct permissions."""
    # Create a bot
    bot_response = client.post(
        "/bots",
        json={"username": "test_bot_permissions", "emoji": "🤖"},
        headers={"X-API-Key": registered_user["api_key"]},
    )
    bot_headers = {"X-API-Key": bot_response.json()["api_key"]}

    # Can read messages
    response = client.get("/messages", headers=bot_headers)
    assert response.status_code == status.HTTP_200_OK

    # Can read users
    response = client.get("/users", headers=bot_headers)
    assert response.status_code == status.HTTP_200_OK

    # Can send room messages
    response = client.post(
        "/messages",
        json={"content": "Bot announcement"},
        headers=bot_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Can update own profile (emoji)
    response = client.patch(
        "/users/me/logo",
        json={"logo": None},  # Bots can only use emoji, but can update
        headers=bot_headers,
    )
    assert response.status_code == status.HTTP_200_OK

    # Cannot send direct messages
    response = client.post(
        "/messages",
        json={"content": "Bot DM", "to_username": registered_user["username"]},
        headers=bot_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_role_persistence_after_update(client: TestClient, registered_user: dict, registered_admin: dict) -> None:
    """Test that role changes persist across requests."""
    admin_headers = {"X-API-Key": registered_admin["api_key"]}
    user_headers = {"X-API-Key": registered_user["api_key"]}

    # Initially user is a member and can send DMs
    # (already tested above, but let's verify)

    # Change user to viewer
    response = client.patch(
        f"/admin/users/{registered_user['username']}/role",
        json={"role": "viewer"},
        headers=admin_headers,
    )
    assert response.status_code == status.HTTP_200_OK

    # Now user shouldn't be able to send messages
    response = client.post(
        "/messages",
        json={"content": "This should fail"},
        headers=user_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # Change back to member
    response = client.patch(
        f"/admin/users/{registered_user['username']}/role",
        json={"role": "member"},
        headers=admin_headers,
    )
    assert response.status_code == status.HTTP_200_OK

    # Now user can send messages again
    response = client.post(
        "/messages",
        json={"content": "This should work"},
        headers=user_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED


def test_legacy_fields_sync_with_role(client: TestClient) -> None:
    """Test that legacy boolean fields (viewer, admin, bot) sync with role."""
    # Register with explicit role
    response = client.post(
        "/register",
        json={"username": "role_sync_test", "role": "admin"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    # Legacy fields should be synced
    assert data["role"] == "admin"
    assert data["admin"] is True
    assert data["viewer"] is False
    assert data["bot"] is False


def test_invalid_role_assignment(client: TestClient, registered_user: dict, registered_admin: dict) -> None:
    """Test that invalid role assignment fails."""
    admin_headers = {"X-API-Key": registered_admin["api_key"]}

    response = client.patch(
        f"/admin/users/{registered_user['username']}/role",
        json={"role": "super_admin"},  # Invalid role
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_role_assignment_to_nonexistent_user(client: TestClient, registered_admin: dict) -> None:
    """Test that assigning role to non-existent user fails."""
    admin_headers = {"X-API-Key": registered_admin["api_key"]}

    response = client.patch(
        "/admin/users/nonexistent_user/role",
        json={"role": "admin"},
        headers=admin_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
