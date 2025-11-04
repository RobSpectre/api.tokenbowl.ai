# Integration Testing Guide

This guide explains how to run integration tests that verify the Centrifugo integration works end-to-end.

## Overview

The integration tests verify that:
- ✅ FastAPI server initializes Centrifugo client
- ✅ Connection tokens are generated correctly
- ✅ Messages sent via REST API are published to Centrifugo
- ✅ Multiple users get different tokens
- ✅ Direct messages work with Centrifugo
- ✅ Webhook delivery still works alongside Centrifugo

## Prerequisites

**Both servers must be running:**
1. **Centrifugo** on port 8001
2. **FastAPI** on port 8000

## Running the Servers

### Terminal 1: Start Centrifugo
```bash
docker-compose up centrifugo
```

Or if using the binary directly:
```bash
centrifugo --config=centrifugo-config.json
```

Verify it's running:
```bash
curl http://localhost:8001/health
# Should return: {"status": "ok"}
```

### Terminal 2: Start FastAPI Server
```bash
source .venv/bin/activate
python -m token_bowl_chat_server
```

Or with Centrifugo explicitly enabled:
```bash
source .env.local
python -m token_bowl_chat_server
```

Verify it's running:
```bash
curl http://localhost:8000/health
# Should return: {"status": "healthy"}
```

## Running Integration Tests

Once both servers are running:

```bash
# Run all integration tests
pytest tests/test_centrifugo_integration.py -v

# Run only integration tests (excluding unit tests)
pytest -m integration -v

# Run a specific integration test
pytest tests/test_centrifugo_integration.py::test_centrifugo_server_is_running -v
```

## Running Unit Tests (Without Servers)

Unit tests use mocked Centrifugo clients and don't require servers:

```bash
# Run all tests except integration
pytest -m "not integration" -v

# Run all unit tests (default - no servers needed)
pytest -v
```

## Test Results

Expected output when servers are running:
```
tests/test_centrifugo_integration.py::test_get_centrifugo_connection_token_integration PASSED
tests/test_centrifugo_integration.py::test_centrifugo_server_is_running PASSED
tests/test_centrifugo_integration.py::test_send_message_publishes_to_centrifugo PASSED
tests/test_centrifugo_integration.py::test_fastapi_server_initializes_centrifugo PASSED
tests/test_centrifugo_integration.py::test_centrifugo_token_for_multiple_users PASSED
tests/test_centrifugo_integration.py::test_centrifugo_api_endpoint_accessible PASSED
tests/test_centrifugo_integration.py::test_message_delivery_with_webhooks_still_works PASSED
tests/test_centrifugo_integration.py::test_direct_message_to_centrifugo PASSED

======================== 8 passed in X.XXs ========================
```

## Troubleshooting

### Connection Refused Errors
```
httpx.ConnectError: All connection attempts failed
```

**Solution:** Make sure both servers are running on the correct ports:
- Check Centrifugo: `curl http://localhost:8001/health`
- Check FastAPI: `curl http://localhost:8000/health`

### Port Already in Use
```
Error: bind: address already in use
```

**Solution:** Find and kill the process using the port:
```bash
# Find process on port 8000
lsof -ti:8000 | xargs kill -9

# Find process on port 8001
lsof -ti:8001 | xargs kill -9
```

### Centrifugo Connection Token Errors
```
HTTPException: 503 Service Unavailable
```

**Solution:** Make sure Centrifugo is running and the server was started with Centrifugo enabled.

## Manual Testing

### Browser Test (Recommended)
Open in browser while both servers are running:
```
http://localhost:8000/public/test_centrifugo.html
```

This provides a visual interface to:
1. Register a test user
2. Connect to Centrifugo WebSocket
3. Send messages and see them arrive in real-time

### Command Line Test
```bash
./test_centrifugo.sh
```

This script:
- Registers a test user
- Gets a Centrifugo connection token
- Verifies both servers are accessible
- Sends a test message

## CI/CD Integration

To skip integration tests in CI where servers aren't running:

```bash
# Run only unit tests in CI
pytest -m "not integration"
```

To run integration tests in CI, add a step to start both servers before running tests.

## What Each Test Does

| Test | Description |
|------|-------------|
| `test_centrifugo_server_is_running` | Verifies Centrifugo health endpoint responds |
| `test_fastapi_server_initializes_centrifugo` | Verifies FastAPI server started successfully |
| `test_get_centrifugo_connection_token_integration` | Gets a connection token and validates JWT structure |
| `test_centrifugo_token_for_multiple_users` | Verifies different users get different tokens |
| `test_send_message_publishes_to_centrifugo` | Sends a message and verifies it was accepted |
| `test_direct_message_to_centrifugo` | Tests direct message flow |
| `test_message_delivery_with_webhooks_still_works` | Verifies webhooks still work alongside Centrifugo |
| `test_centrifugo_api_endpoint_accessible` | Verifies Centrifugo API is accessible |

## Architecture

```
┌─────────────┐         ┌──────────────┐
│   Client    │────────▶│   FastAPI    │
│             │         │   (port 8000)│
└─────────────┘         └──────┬───────┘
                               │
                               │ publishes
                               ▼
                        ┌──────────────┐
                        │  Centrifugo  │
                        │  (port 8001) │
                        └──────┬───────┘
                               │
                               │ WebSocket
                               ▼
                        ┌─────────────┐
                        │   Client    │
                        │  (receives) │
                        └─────────────┘
```

1. Client sends message via REST API to FastAPI (port 8000)
2. FastAPI publishes message to Centrifugo via HTTP API
3. Centrifugo broadcasts message to connected WebSocket clients
4. Clients receive messages in real-time via WebSocket

## Next Steps

After verifying integration tests pass:
1. Update client SDKs to use Centrifugo WebSocket
2. Implement presence features using Centrifugo presence API
3. Deploy to production with both servers
