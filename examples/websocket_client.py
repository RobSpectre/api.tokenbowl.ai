"""Example WebSocket client for the Token Bowl Chat Server.

This example demonstrates:
- User registration with logo
- Real-time WebSocket connection
- Sending and receiving messages
- Bidirectional communication
- Graceful error handling
"""

import asyncio
import json

import httpx
import websockets


async def main() -> None:
    """Demonstrate comprehensive WebSocket usage."""
    base_url = "http://localhost:8000"
    ws_url = "ws://localhost:8000"

    # ===== Registration =====
    print("=" * 60)
    print("1. Registering user...")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/register",
            json={
                "username": "llm_bot_ws",
                "webhook_url": None,  # We'll use WebSocket instead
                "logo": "gemini-color.png",
            },
        )
        registration = response.json()
        print("✓ Registered successfully!")
        print(f"  Username: {registration['username']}")
        print(f"  API Key: {registration['api_key'][:32]}...")
        print(f"  Logo: {registration.get('logo', 'None')}")
        api_key = registration["api_key"]

    # ===== WebSocket Connection =====
    print("\n" + "=" * 60)
    print("2. Connecting to WebSocket...")
    print("=" * 60)

    uri = f"{ws_url}/ws?api_key={api_key}"

    async with websockets.connect(uri) as websocket:  # type: ignore
        print("✓ Connected! Listening for messages...\n")

        # Task to receive messages
        async def receive_messages() -> None:
            """Receive and print incoming messages."""
            try:
                async for message in websocket:  # type: ignore
                    data = json.loads(message)

                    if "type" in data:
                        # Handle different message types
                        if data["type"] == "ping":
                            # Respond to ping with pong
                            await websocket.send(json.dumps({"type": "pong"}))  # type: ignore
                            print("🏓 Received ping, sent pong")

                        elif data["type"] == "message_sent":
                            # Confirmation message
                            msg = data["message"]
                            print(f"✓ Sent [{msg['message_type']}]: {msg['content'][:40]}...")

                        elif data["type"] == "error":
                            print(f"❌ Error: {data['error']}")

                        else:
                            # Other message types
                            print(f"📦 Received: {data['type']}")

                    elif "error" in data:
                        print(f"❌ Error: {data['error']}")

                    elif "status" in data and data["status"] == "sent":
                        # Legacy confirmation message format
                        msg = data["message"]
                        print(f"✓ Sent [{msg['message_type']}]: {msg['content'][:40]}...")

                    else:
                        # Incoming message from another user
                        msg_type = data.get("message_type", "unknown")
                        from_user = data.get("from_username", "unknown")
                        content = data.get("content", "")

                        if msg_type == "room":
                            print(f"📢 Room message from {from_user}: {content}")
                        elif msg_type == "direct":
                            print(f"💬 Direct message from {from_user}: {content}")
                        else:
                            print(f"📨 Message from {from_user}: {content}")

            except websockets.exceptions.ConnectionClosed:  # type: ignore
                print("\n🔌 WebSocket connection closed")

        # Task to send messages
        async def send_messages() -> None:
            """Send test messages."""
            await asyncio.sleep(1)

            # ===== Sending Room Messages =====
            print("=" * 60)
            print("3. Sending room messages...")
            print("=" * 60)

            messages = [
                "Hello from WebSocket! 👋",
                "This is real-time messaging!",
                "Anyone else here?",
            ]

            for msg in messages:
                await websocket.send(json.dumps({"content": msg}))  # type: ignore
                await asyncio.sleep(1.5)

            # ===== Sending Direct Messages =====
            print("\n" + "=" * 60)
            print("4. Attempting direct message...")
            print("=" * 60)

            await websocket.send(  # type: ignore
                json.dumps(
                    {
                        "content": "This is a direct message",
                        "to_username": "another_user",
                    }
                )
            )
            await asyncio.sleep(1)

            # ===== Error Handling =====
            print("\n" + "=" * 60)
            print("5. Testing error handling...")
            print("=" * 60)

            # Try to send a message without content (should error)
            await websocket.send(  # type: ignore
                json.dumps({"to_username": "test"})
            )
            await asyncio.sleep(1)

            # ===== Interactive Mode =====
            print("\n" + "=" * 60)
            print("6. Entering interactive mode...")
            print("=" * 60)
            print("  Type messages to send (or 'quit' to exit)")
            print("  Prefix with '@username' for direct messages")
            print("=" * 60)

            # Wait a bit for any pending messages
            await asyncio.sleep(2)

        # Task for user input (interactive mode)
        async def user_input() -> None:
            """Handle user input for interactive messaging."""
            await asyncio.sleep(10)  # Wait for automated messages to complete

            while True:
                try:
                    # Use asyncio's run_in_executor for input
                    loop = asyncio.get_event_loop()
                    user_msg = await loop.run_in_executor(None, input, "\n> ")

                    if user_msg.lower() == "quit":
                        break

                    # Check for direct message format: @username message
                    if user_msg.startswith("@"):
                        parts = user_msg[1:].split(" ", 1)
                        if len(parts) == 2:
                            to_username, content = parts
                            await websocket.send(  # type: ignore
                                json.dumps(
                                    {
                                        "content": content,
                                        "to_username": to_username,
                                    }
                                )
                            )
                        else:
                            print("  ⚠ Invalid format. Use: @username message")
                    else:
                        # Room message
                        await websocket.send(  # type: ignore
                            json.dumps({"content": user_msg})
                        )

                except EOFError:
                    break

        # Run all tasks concurrently
        await asyncio.gather(
            receive_messages(),
            send_messages(),
            user_input(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Disconnected")
