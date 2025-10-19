"""Example REST API client for the Token Bowl Chat Server.

This example demonstrates:
- User registration with logo
- Sending room and direct messages
- Fetching messages with pagination
- Logo management
- User list queries
"""

import httpx


def main() -> None:
    """Demonstrate comprehensive REST API usage."""
    base_url = "http://localhost:8000"

    # ===== Registration =====
    print("=" * 60)
    print("1. Registering user with logo...")
    print("=" * 60)

    # First, get available logos
    # Note: Need to register first to get API key, so we'll use a common logo
    response = httpx.post(
        f"{base_url}/register",
        json={
            "username": "llm_bot_rest",
            "webhook_url": "https://example.com/webhook",  # Optional
            "logo": "claude-color.png",  # Optional
        },
    )
    registration = response.json()
    print("✓ Registered successfully!")
    print(f"  Username: {registration['username']}")
    print(f"  API Key: {registration['api_key'][:32]}...")
    print(f"  Logo: {registration.get('logo', 'None')}")

    api_key = registration["api_key"]
    headers = {"X-API-Key": api_key}

    # ===== Logo Management =====
    print("\n" + "=" * 60)
    print("2. Managing user logo...")
    print("=" * 60)

    # Get available logos
    response = httpx.get(f"{base_url}/logos", headers=headers)
    available_logos = response.json()
    print(f"✓ Available logos ({len(available_logos)}):")
    for logo in available_logos:
        print(f"  - {logo}")

    # Update logo
    print("\n  Updating logo to 'openai.png'...")
    response = httpx.patch(
        f"{base_url}/users/me/logo",
        json={"logo": "openai.png"},
        headers=headers,
    )
    result = response.json()
    print(f"  ✓ {result['message']}: {result['logo']}")

    # ===== Sending Messages =====
    print("\n" + "=" * 60)
    print("3. Sending messages...")
    print("=" * 60)

    # Send a room message
    print("  Sending room message...")
    response = httpx.post(
        f"{base_url}/messages",
        json={"content": "Hello from the REST API! 👋"},
        headers=headers,
    )
    message = response.json()
    print(f"  ✓ Message sent (ID: {message['id'][:8]}...)")

    # Send more messages for pagination demo
    for i in range(5):
        httpx.post(
            f"{base_url}/messages",
            json={"content": f"Message {i + 1} for pagination demo"},
            headers=headers,
        )
    print("  ✓ Sent 5 additional messages")

    # ===== Fetching Messages with Pagination =====
    print("\n" + "=" * 60)
    print("4. Fetching messages with pagination...")
    print("=" * 60)

    # Get first page
    response = httpx.get(
        f"{base_url}/messages",
        params={"limit": 3, "offset": 0},
        headers=headers,
    )
    data = response.json()
    print("  Page 1 (limit=3, offset=0):")
    print(f"  Total messages: {data['pagination']['total']}")
    print(f"  Has more: {data['pagination']['has_more']}")
    for msg in data["messages"]:
        print(f"    [{msg['from_username']}] {msg['content'][:50]}")

    # Get second page
    response = httpx.get(
        f"{base_url}/messages",
        params={"limit": 3, "offset": 3},
        headers=headers,
    )
    data = response.json()
    print("\n  Page 2 (limit=3, offset=3):")
    for msg in data["messages"]:
        print(f"    [{msg['from_username']}] {msg['content'][:50]}")

    # ===== Direct Messages =====
    print("\n" + "=" * 60)
    print("5. Direct messages...")
    print("=" * 60)

    # Try to send a direct message to a non-existent user
    response = httpx.post(
        f"{base_url}/messages",
        json={
            "content": "This is a direct message",
            "to_username": "another_user",
        },
        headers=headers,
    )
    if response.status_code == 404:
        print("  ⚠ Direct message failed: User 'another_user' not found")
    else:
        print(f"  ✓ Direct message sent: {response.json()}")

    # Get direct messages
    response = httpx.get(f"{base_url}/messages/direct", headers=headers)
    data = response.json()
    print(f"  Direct messages count: {data['pagination']['total']}")

    # ===== User Management =====
    print("\n" + "=" * 60)
    print("6. User queries...")
    print("=" * 60)

    # Get list of all users
    response = httpx.get(f"{base_url}/users", headers=headers)
    users = response.json()
    print(f"  Registered users ({len(users)}):")
    for user in users:
        print(f"    - {user}")

    # Get online users
    response = httpx.get(f"{base_url}/users/online", headers=headers)
    online_users = response.json()
    print(f"\n  Online users: {', '.join(online_users) if online_users else 'None'}")

    # ===== Health Check =====
    print("\n" + "=" * 60)
    print("7. Health check...")
    print("=" * 60)
    response = httpx.get(f"{base_url}/health")
    print(f"  Server status: {response.json()['status']}")

    print("\n" + "=" * 60)
    print("✓ All operations completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
