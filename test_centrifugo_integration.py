#!/usr/bin/env python3
"""Test script to verify Centrifugo integration works end-to-end."""

import asyncio
import json
import sys

import httpx
from centrifuge import Client as CentrifugoClient

# Configuration
API_BASE_URL = "http://localhost:8000"
CENTRIFUGO_WS_URL = "ws://localhost:8001/connection/websocket"


async def main():
    """Test Centrifugo integration end-to-end."""
    print("🧪 Testing Centrifugo Integration\n")
    print("=" * 60)

    # Step 1: Register a test user (or use existing)
    print("\n📝 Step 1: Register test user...")
    async with httpx.AsyncClient() as http:
        try:
            response = await http.post(
                f"{API_BASE_URL}/register",
                json={"username": "centrifugo_test_user"},
            )
            if response.status_code == 201:
                user_data = response.json()
                api_key = user_data["api_key"]
                username = user_data["username"]
                print(f"✅ Registered user: {username}")
            elif response.status_code == 409:
                # User already exists, that's fine
                print("⚠️  User already exists, continuing...")
                # For demo, we'll need to provide an API key
                print("❌ Cannot continue - need to use existing API key")
                print("   Tip: Delete the user first or provide API key")
                return
            else:
                print(f"❌ Failed to register: {response.status_code}")
                print(response.text)
                return
        except Exception as e:
            print(f"❌ Error registering user: {e}")
            return

    # Step 2: Get Centrifugo connection token
    print("\n🎫 Step 2: Get Centrifugo connection token...")
    try:
        response = await http.get(
            f"{API_BASE_URL}/centrifugo/connection-token",
            headers={"X-API-Key": api_key},
        )
        if response.status_code != 200:
            print(f"❌ Failed to get token: {response.status_code}")
            print(response.text)
            return

        token_data = response.json()
        centrifugo_token = token_data["token"]
        centrifugo_url = token_data["url"]
        channels = token_data["channels"]
        print("✅ Got connection token")
        print(f"   Channels: {channels}")
    except Exception as e:
        print(f"❌ Error getting token: {e}")
        return

    # Step 3: Connect to Centrifugo
    print("\n🔌 Step 3: Connect to Centrifugo WebSocket...")

    received_messages = []

    def on_message(ctx):
        """Handle incoming messages."""
        print("\n📨 Received message via Centrifugo:")
        print(f"   Channel: {ctx.channel}")
        print(f"   Data: {json.dumps(ctx.data, indent=2)}")
        received_messages.append(ctx.data)

    try:
        # Create Centrifugo client
        centrifugo = CentrifugoClient(
            centrifugo_url,
            token=centrifugo_token,
        )

        # Subscribe to room channel
        room_sub = centrifugo.new_subscription("room:main")
        room_sub.on_publication(on_message)

        # Subscribe to personal channel
        user_sub = centrifugo.new_subscription(f"user:{username}")
        user_sub.on_publication(on_message)

        print("✅ Created Centrifugo client")
        print(f"   Subscribed to: room:main, user:{username}")

        # Connect
        centrifugo.connect()
        print("✅ Connected to Centrifugo!")

        # Wait a moment for connection to establish
        await asyncio.sleep(1)

    except Exception as e:
        print(f"❌ Error connecting to Centrifugo: {e}")
        import traceback

        traceback.print_exc()
        return

    # Step 4: Send a message via REST API
    print("\n📤 Step 4: Send a room message via REST API...")
    try:
        response = await http.post(
            f"{API_BASE_URL}/messages",
            json={"content": "Hello from Centrifugo integration test! 🎉"},
            headers={"X-API-Key": api_key},
        )
        if response.status_code != 201:
            print(f"❌ Failed to send message: {response.status_code}")
            print(response.text)
            centrifugo.disconnect()
            return

        message_data = response.json()
        print("✅ Message sent via REST API")
        print(f"   Message ID: {message_data['id']}")
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        centrifugo.disconnect()
        return

    # Step 5: Wait for message to arrive via Centrifugo
    print("\n⏳ Step 5: Waiting for message via Centrifugo...")

    # Wait up to 5 seconds for the message
    for _ in range(10):
        await asyncio.sleep(0.5)
        if received_messages:
            break

    # Step 6: Verify results
    print("\n" + "=" * 60)
    if received_messages:
        print("✅ SUCCESS! Message received via Centrifugo")
        print(f"\nReceived {len(received_messages)} message(s)")
        for msg in received_messages:
            print(f"  - {msg.get('from_username')}: {msg.get('content')}")
    else:
        print("❌ FAILED! No message received via Centrifugo")
        print("   Check that:")
        print("   1. Centrifugo is running on port 8001")
        print("   2. FastAPI is running on port 8000")
        print("   3. Both servers are configured correctly")

    # Cleanup
    print("\n🧹 Cleaning up...")
    centrifugo.disconnect()
    print("✅ Disconnected from Centrifugo")

    print("\n" + "=" * 60)
    if received_messages:
        print("🎉 Centrifugo integration is working!\n")
        sys.exit(0)
    else:
        print("❌ Centrifugo integration test failed\n")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
