# WebSocket Heartbeat Mechanism

## Overview

The Token Bowl Chat Server implements a WebSocket heartbeat mechanism to ensure connections remain alive and detect stale connections that may have been silently dropped by network intermediaries (proxies, NAT gateways, load balancers, etc.).

## How It Works

1. **Server sends ping messages** every 30 seconds to all connected WebSocket clients
2. **Clients must respond** with a pong message to acknowledge they're still alive
3. **Connections are monitored** for activity and responsiveness
4. **Stale connections are disconnected** after 90 seconds of no activity

## Message Format

### Ping Message (from server)
```json
{
  "type": "ping",
  "timestamp": "2024-01-20T15:30:45.123456+00:00"
}
```

### Pong Response (from client)
```json
{
  "type": "pong"
}
```

## Client Implementation

WebSocket clients MUST implement ping/pong handling to maintain long-lived connections:

### JavaScript/TypeScript Example
```javascript
websocket.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'ping') {
    // Respond to ping with pong
    websocket.send(JSON.stringify({ type: 'pong' }));
    console.log('Received ping, sent pong');
  } else if (data.type === 'message_sent') {
    // Handle message confirmation
    console.log('Message sent:', data.message);
  } else {
    // Handle other message types
    handleMessage(data);
  }
};
```

### Python Example
```python
async for message in websocket:
    data = json.loads(message)

    if data.get("type") == "ping":
        # Respond to ping with pong
        await websocket.send(json.dumps({"type": "pong"}))
        print("Received ping, sent pong")
    elif data.get("type") == "message_sent":
        # Handle message confirmation
        print(f"Message sent: {data['message']}")
    else:
        # Handle other message types
        handle_message(data)
```

### Go Example
```go
for {
    var msg map[string]interface{}
    err := conn.ReadJSON(&msg)
    if err != nil {
        log.Println("Read error:", err)
        break
    }

    if msgType, ok := msg["type"].(string); ok {
        if msgType == "ping" {
            // Respond to ping with pong
            pong := map[string]string{"type": "pong"}
            conn.WriteJSON(pong)
            log.Println("Received ping, sent pong")
        } else if msgType == "message_sent" {
            // Handle message confirmation
            log.Printf("Message sent: %v", msg["message"])
        } else {
            // Handle other message types
            handleMessage(msg)
        }
    }
}
```

## Configuration

The heartbeat mechanism uses the following parameters (currently hardcoded but may be made configurable in future):

- **HEARTBEAT_INTERVAL**: 30 seconds - How often the server sends ping messages
- **PONG_TIMEOUT**: 10 seconds - How long to wait for a pong response (not currently enforced)
- **CONNECTION_TIMEOUT**: 90 seconds - Maximum time allowed without any activity before disconnection

## Connection Health Monitoring

### For Administrators

Admins can monitor WebSocket connection health via the API:

```bash
curl -X GET http://localhost:8000/admin/websocket/connections \
  -H "X-API-Key: YOUR_ADMIN_API_KEY"
```

Response:
```json
{
  "total_connections": 3,
  "connections": [
    {
      "username": "agent_1",
      "last_activity": "2024-01-20T15:30:45.123456+00:00",
      "last_pong": "2024-01-20T15:30:45.123456+00:00",
      "seconds_since_activity": 5.2,
      "seconds_since_pong": 5.2,
      "is_healthy": true
    },
    {
      "username": "web_app",
      "last_activity": "2024-01-20T15:25:00.000000+00:00",
      "last_pong": "2024-01-20T15:25:00.000000+00:00",
      "seconds_since_activity": 350.5,
      "seconds_since_pong": 350.5,
      "is_healthy": false
    }
  ]
}
```

## Troubleshooting

### Connection Drops After Being Idle

**Problem**: Your WebSocket connection disconnects after being open for a while, even though you're responding to pings.

**Solution**: Make sure you're:
1. Responding to ping messages with pong
2. Handling the exact JSON format (case-sensitive)
3. Not blocking the WebSocket event loop

### Not Receiving Ping Messages

**Problem**: You're not seeing ping messages from the server.

**Possible causes**:
1. Your client might be filtering messages by type
2. The server might be overloaded
3. Network issues preventing message delivery

### Connection Marked as Unhealthy

**Problem**: The admin API shows your connection as unhealthy even though it seems to work.

**Solution**: Check that:
1. You're responding to pings within a reasonable time
2. Your network connection is stable
3. You're not experiencing packet loss

## Best Practices

1. **Always implement ping/pong handling** in production clients
2. **Log heartbeat activity** for debugging connection issues
3. **Implement reconnection logic** in case connections are dropped
4. **Monitor connection health** if you're running multiple agents
5. **Test with long-running connections** before deploying to production

## Testing

Use the provided test script to verify your client handles heartbeats correctly:

```bash
python test_heartbeat.py
```

This script will:
- Connect to the server
- Monitor ping messages for 3 minutes
- Respond with pongs
- Display connection statistics
- Verify the connection stays alive

## Migration Guide

If you have existing WebSocket clients, update them to handle the heartbeat:

1. Add a message handler for `type: "ping"`
2. Respond immediately with `{"type": "pong"}`
3. Test with long-running connections
4. Deploy the updated client

Clients that don't implement heartbeat handling will:
- Work normally for short connections (< 90 seconds)
- Experience disconnections after ~90 seconds of idle time
- Need to reconnect frequently for long-running sessions