#!/bin/bash
# Quick Centrifugo integration test

echo "🧪 Testing Centrifugo Integration"
echo "=================================="
echo

# Register a test user
echo "📝 Registering test user..."
USER_RESPONSE=$(curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"test_$(date +%s)\"}")

API_KEY=$(echo $USER_RESPONSE | jq -r '.api_key')
USERNAME=$(echo $USER_RESPONSE | jq -r '.username')

if [ "$API_KEY" = "null" ]; then
  echo "❌ Failed to register user"
  echo $USER_RESPONSE | jq
  exit 1
fi

echo "✅ User registered: $USERNAME"
echo

# Get Centrifugo token
echo "🎫 Getting Centrifugo connection token..."
TOKEN_RESPONSE=$(curl -s http://localhost:8000/centrifugo/connection-token \
  -H "X-API-Key: $API_KEY")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.token')
WS_URL=$(echo $TOKEN_RESPONSE | jq -r '.url')

if [ "$TOKEN" = "null" ]; then
  echo "❌ Failed to get Centrifugo token"
  echo $TOKEN_RESPONSE | jq
  exit 1
fi

echo "✅ Got Centrifugo token"
echo "   URL: $WS_URL"
echo "   Channels:"
echo $TOKEN_RESPONSE | jq -r '.channels[]' | sed 's/^/     - /'
echo

# Verify Centrifugo is accessible
echo "🔌 Checking Centrifugo health..."
CENTRIFUGO_HEALTH=$(curl -s http://localhost:8001/health)
if [ $? -eq 0 ]; then
  echo "✅ Centrifugo is running and accessible"
else
  echo "❌ Cannot reach Centrifugo on port 8001"
  exit 1
fi
echo

# Send a test message
echo "📤 Sending test message via REST API..."
MSG_RESPONSE=$(curl -s -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"content":"Test message from integration test! 🎉"}')

MSG_ID=$(echo $MSG_RESPONSE | jq -r '.id')

if [ "$MSG_ID" = "null" ]; then
  echo "❌ Failed to send message"
  echo $MSG_RESPONSE | jq
  exit 1
fi

echo "✅ Message sent successfully"
echo "   Message ID: $MSG_ID"
echo

echo "=================================="
echo "✅ All API endpoints working!"
echo
echo "To fully test WebSocket message delivery:"
echo "  Open: http://localhost:8000/public/test_centrifugo.html"
echo
