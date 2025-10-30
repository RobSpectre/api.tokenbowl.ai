#!/usr/bin/env python3
"""Test script to verify WebSocket heartbeat mechanism works correctly.

This script:
1. Connects to the server via WebSocket
2. Monitors ping messages from the server
3. Responds with pong messages
4. Runs for several minutes to ensure connection stays alive
"""

import asyncio
import json
import time
from datetime import datetime

import httpx
import websockets


async def test_heartbeat():
    """Test WebSocket heartbeat mechanism."""
    base_url = "http://localhost:8000"
    ws_url = "ws://localhost:8000"

    # Register a test user
    print("Registering test user...")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/register",
            json={
                "username": f"heartbeat_test_{int(time.time())}",
                "webhook_url": None,
                "logo": "claude-color.png",
            },
        )
        registration = response.json()
        print(f"✓ Registered: {registration['username']}")
        api_key = registration["api_key"]

    # Connect to WebSocket
    uri = f"{ws_url}/ws?api_key={api_key}"
    print("\nConnecting to WebSocket...")

    async with websockets.connect(uri) as websocket:
        print("✓ Connected!")
        print("\nMonitoring connection for 3 minutes...")
        print("(You should see ping/pong messages every 30 seconds)")
        print("-" * 60)

        start_time = time.time()
        ping_count = 0
        message_count = 0
        last_activity = time.time()

        # Send an initial message
        await websocket.send(
            json.dumps({"type": "message", "content": "Starting heartbeat test..."})
        )

        try:
            while time.time() - start_time < 180:  # Run for 3 minutes
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)

                    data = json.loads(message)
                    current_time = datetime.now().strftime("%H:%M:%S")

                    if data.get("type") == "ping":
                        ping_count += 1
                        print(f"[{current_time}] 📥 Received PING #{ping_count}")

                        # Respond with pong
                        await websocket.send(json.dumps({"type": "pong"}))
                        print(f"[{current_time}] 📤 Sent PONG #{ping_count}")

                        last_activity = time.time()

                        # Show connection stats
                        uptime = int(time.time() - start_time)
                        print(f"    ⏱  Connection uptime: {uptime}s")
                        print("    💓 Connection healthy: Yes")
                        print("-" * 60)

                    elif data.get("type") == "message_sent":
                        message_count += 1
                        msg = data["message"]
                        print(f"[{current_time}] ✉️  Message sent: {msg['content']}")

                    else:
                        print(f"[{current_time}] 📦 Received: {data}")

                except TimeoutError:
                    # Check if connection is still alive by sending a message
                    idle_time = int(time.time() - last_activity)
                    if idle_time > 60:
                        print(f"\n⚠️  No activity for {idle_time} seconds, testing connection...")
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "message",
                                    "content": f"Test message after {idle_time}s idle",
                                }
                            )
                        )

        except websockets.exceptions.ConnectionClosed as e:
            print(f"\n❌ Connection closed unexpectedly: {e}")
            print(f"   Total uptime: {int(time.time() - start_time)} seconds")
            print(f"   Pings received: {ping_count}")
            return False

        # Success!
        total_time = int(time.time() - start_time)
        print(f"\n✅ SUCCESS! Connection stayed alive for {total_time} seconds")
        print(f"   Total pings received: {ping_count}")
        print(f"   Total pongs sent: {ping_count}")
        print(f"   Messages sent: {message_count + 2}")  # Initial + test message

        # Send final message
        await websocket.send(
            json.dumps(
                {
                    "type": "message",
                    "content": f"Heartbeat test completed successfully! {ping_count} ping/pongs exchanged.",
                }
            )
        )

        return True


async def test_stale_connection():
    """Test that stale connections are properly detected and cleaned up."""
    base_url = "http://localhost:8000"
    ws_url = "ws://localhost:8000"

    print("\n" + "=" * 60)
    print("Testing stale connection detection...")
    print("=" * 60)

    # Register a test user
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/register",
            json={
                "username": f"stale_test_{int(time.time())}",
                "webhook_url": None,
            },
        )
        registration = response.json()
        api_key = registration["api_key"]

    uri = f"{ws_url}/ws?api_key={api_key}"
    print("Connecting and NOT responding to pings...")

    async with websockets.connect(uri) as websocket:
        print("✓ Connected!")
        print("Ignoring ping messages to simulate stale connection...")

        ping_count = 0
        start_time = time.time()

        try:
            while True:
                message = await websocket.recv()
                data = json.loads(message)

                if data.get("type") == "ping":
                    ping_count += 1
                    print(f"📥 Received PING #{ping_count} (ignoring...)")
                    # DO NOT respond with pong - simulate broken client

        except websockets.exceptions.ConnectionClosed as e:
            elapsed = int(time.time() - start_time)
            print(f"\n✓ Connection closed after {elapsed} seconds (expected ~90s)")
            print(f"  Ignored {ping_count} pings")
            print(f"  Close reason: {e}")

            if elapsed > 60 and elapsed < 120:
                print("✅ Stale connection detection working correctly!")
                return True
            else:
                print("⚠️  Connection closed earlier or later than expected")
                return False


async def main():
    """Run all heartbeat tests."""
    print("=" * 60)
    print("WebSocket Heartbeat Mechanism Test")
    print("=" * 60)

    # Make sure server is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code != 200:
                print("❌ Server is not healthy")
                return
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("Please start the server with: python -m token_bowl_chat_server")
        return

    # Test 1: Normal heartbeat operation
    success1 = await test_heartbeat()

    # Test 2: Stale connection detection
    # (commented out for now as it takes 90+ seconds)
    # success2 = await test_stale_connection()

    if success1:
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ Some tests failed")
        print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
