#!/usr/bin/env python3
"""Diagnostic script to test Centrifugo publishing."""

import asyncio
import sys

from cent import AsyncClient
from cent.dto import PublishRequest


async def test_publish():
    """Test publishing to Centrifugo."""
    print("🔍 Diagnosing Centrifugo Connection\n")
    print("=" * 60)

    # Connect to Centrifugo
    print("\n1️⃣ Creating Centrifugo client...")
    client = AsyncClient(
        "http://localhost:8001/api",
        api_key="your-api-key-change-in-production",
        timeout=3.0,
    )
    print("✅ Client created")

    # Try to publish a test message
    print("\n2️⃣ Publishing test message to room:main...")
    try:
        request = PublishRequest(
            channel="room:main",
            data={
                "test": "diagnostic message",
                "content": "This is a diagnostic test",
            },
        )
        result = await client.publish(request)
        print("✅ Publish successful!")
        print(f"   Result: {result}")
    except Exception as e:
        print("❌ Publish failed!")
        print(f"   Error: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("✅ Centrifugo is working correctly!")
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_publish())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
