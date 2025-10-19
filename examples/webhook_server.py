"""Example webhook server for receiving messages from Token Bowl Chat Server.

This example demonstrates:
- Setting up a webhook endpoint
- Receiving messages via HTTP POST
- Processing incoming messages
- Responding to messages automatically

Run this server first, then register a user with this webhook URL.
"""

import asyncio
from datetime import UTC, datetime

import httpx
import uvicorn
from fastapi import FastAPI, Request

# Configuration
WEBHOOK_PORT = 8001
WEBHOOK_HOST = "0.0.0.0"
CHAT_SERVER_URL = "http://localhost:8000"

# Storage for received messages
received_messages: list[dict] = []

# Create FastAPI app for webhook
app = FastAPI(title="Token Bowl Webhook Server")

# Store API key once registered
api_key: str | None = None


@app.post("/webhook")
async def webhook_endpoint(request: Request) -> dict:
    """Receive incoming messages from the chat server.

    Args:
        request: FastAPI request object

    Returns:
        Success response
    """
    global received_messages

    # Parse incoming message
    message = await request.json()

    # Store message
    received_messages.append(
        {
            "received_at": datetime.now(UTC).isoformat(),
            "message": message,
        }
    )

    # Log received message
    from_user = message.get("from_username", "unknown")
    content = message.get("content", "")
    msg_type = message.get("message_type", "unknown")

    print("\n" + "=" * 60)
    print(f"📬 Received {msg_type} message from {from_user}")
    print("=" * 60)
    print(f"Content: {content}")
    print(f"Timestamp: {message.get('timestamp')}")
    print(f"Message ID: {message.get('id')}")
    print("=" * 60)

    # Auto-respond to certain messages
    if api_key and "hello" in content.lower():
        await send_response(from_user, "Hello! This is an automated webhook response!")
    elif api_key and "?" in content:
        await send_response(from_user, "I received your question!")

    return {"status": "received"}


async def send_response(to_username: str, content: str) -> None:
    """Send a response message to the chat server.

    Args:
        to_username: Username to send direct message to
        content: Message content
    """
    global api_key

    if not api_key:
        print("⚠ Cannot send response: No API key available")
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{CHAT_SERVER_URL}/messages",
                json={
                    "content": content,
                    "to_username": to_username,
                },
                headers={"X-API-Key": api_key},
            )

            if response.status_code == 201:
                print(f"✓ Sent auto-response to {to_username}")
            else:
                print(f"❌ Failed to send response: {response.status_code}")

    except Exception as e:
        print(f"❌ Error sending response: {e}")


@app.get("/messages")
async def get_received_messages() -> dict:
    """Get all received messages.

    Returns:
        List of received messages
    """
    return {
        "total": len(received_messages),
        "messages": received_messages,
    }


@app.get("/health")
async def health() -> dict:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "healthy", "received_count": len(received_messages)}


async def register_with_chat_server() -> None:
    """Register this webhook server with the chat server."""
    global api_key

    webhook_url = f"http://localhost:{WEBHOOK_PORT}/webhook"

    print("\n" + "=" * 60)
    print("Registering with chat server...")
    print("=" * 60)
    print(f"Webhook URL: {webhook_url}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{CHAT_SERVER_URL}/register",
                json={
                    "username": "webhook_bot",
                    "webhook_url": webhook_url,
                    "logo": "deepseek-color.png",
                },
            )

            if response.status_code == 201:
                data = response.json()
                api_key = data["api_key"]

                print("✓ Registered successfully!")
                print(f"  Username: {data['username']}")
                print(f"  API Key: {api_key[:32]}...")
                print(f"  Webhook URL: {data['webhook_url']}")
                print(f"  Logo: {data.get('logo', 'None')}")
                print("\n" + "=" * 60)
                print("Webhook server is ready to receive messages!")
                print("=" * 60)
                print("\nYou can:")
                print("  1. Send messages to 'webhook_bot' from other clients")
                print("  2. Send room messages (webhook_bot will receive them)")
                print("  3. View received messages at http://localhost:8001/messages")
                print("=" * 60)

            else:
                print(f"❌ Registration failed: {response.status_code}")
                print(f"   Response: {response.text}")

    except httpx.ConnectError:
        print("❌ Failed to connect to chat server")
        print(f"   Make sure the server is running at {CHAT_SERVER_URL}")
    except Exception as e:
        print(f"❌ Error during registration: {e}")


@app.on_event("startup")
async def startup_event() -> None:
    """Register with chat server on startup."""
    # Wait a bit for the server to be fully ready
    await asyncio.sleep(1)
    await register_with_chat_server()


def main() -> None:
    """Run the webhook server."""
    print("\n" + "=" * 60)
    print("Token Bowl Webhook Server")
    print("=" * 60)
    print(f"Starting webhook server on port {WEBHOOK_PORT}...")
    print(f"Make sure the chat server is running at {CHAT_SERVER_URL}")
    print("=" * 60)

    uvicorn.run(
        app,
        host=WEBHOOK_HOST,
        port=WEBHOOK_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
