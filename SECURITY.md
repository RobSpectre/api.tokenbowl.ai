# Security Configuration

## Overview

This document describes the security model for the Token Bowl Chat Server with Centrifugo integration.

## Authentication Flow

```
User → FastAPI (validates credentials) → Issues JWT token → Centrifugo (validates JWT)
```

### 1. FastAPI Authentication

**Endpoints require authentication:**
- `/centrifugo/connection-token` - Requires valid API key or Stytch session
- `/messages` - Requires valid API key or Stytch session
- All other protected endpoints

**Authentication methods:**
- API Key: `X-API-Key: <user_api_key>` header
- Stytch Session: `Authorization: Bearer <stytch_token>` header

### 2. Centrifugo JWT Tokens

**Token generation** (`centrifugo_client.py`):
```python
claims = {
    "sub": user.username,  # User identity
    "exp": <24_hours_from_now>,  # Expiration
    "iat": <current_time>,  # Issued at
    "channels": [  # Channel permissions
        "room:main",
        f"user:{user.username}"
    ]
}
```

**Token validation:**
- Signed with `token_hmac_secret_key` (HMAC-SHA256)
- Verified by Centrifugo on connection
- Grants access only to channels in `channels` claim

### 3. Centrifugo Security Settings

**Required configuration** (`centrifugo-config.json`):
```json
{
  "token_hmac_secret_key": "your-secret-key-change-in-production",
  "client_insecure": false,
  "client_anonymous": false,
  "namespaces": [
    {
      "name": "room",
      "publish": false,
      "subscribe_to_publish": true
    },
    {
      "name": "user",
      "publish": false,
      "subscribe_to_user": true
    }
  ]
}
```

**Critical settings:**
- `client_insecure: false` - Disables insecure client mode
- `client_anonymous: false` - **Requires JWT token for all connections**
- `subscribe_to_publish: true` - Users need publish permission to subscribe to room
- `subscribe_to_user: true` - Users can only subscribe to their own user channel
- `publish: false` - Clients cannot publish directly (only server via API)

## Security Guarantees

### ✅ What IS Protected

1. **No anonymous access** - All connections require valid JWT token from FastAPI
2. **User identity verified** - JWT `sub` claim contains authenticated username
3. **Channel permissions** - JWT `channels` claim restricts subscription access
4. **Time-limited tokens** - Tokens expire after 24 hours
5. **Server-only publishing** - Only FastAPI can publish (via Centrifugo API with API key)
6. **User isolation** - Users can only subscribe to their own `user:username` channel
7. **No token forgery** - JWTs signed with secret, validated by Centrifugo

### ❌ What Clients CANNOT Do

- Connect to Centrifugo without a valid JWT token
- Subscribe to channels not in their token's `channels` claim
- Subscribe to other users' channels (enforced by `subscribe_to_user: true`)
- Publish messages directly to Centrifugo (only server can publish via API)
- Forge or modify JWT tokens (cryptographically signed)
- Use expired tokens (Centrifugo validates expiration)

## Secrets Management

### Required Secrets

**Must match between FastAPI and Centrifugo:**

1. **`token_hmac_secret_key`** (Centrifugo) = **`CENTRIFUGO_TOKEN_SECRET`** (FastAPI)
   - Used to sign and verify JWT tokens
   - **CRITICAL:** Must be kept secret and changed from default
   - Minimum 32 bytes, use cryptographically random value

2. **`api_key`** (Centrifugo) = **`CENTRIFUGO_API_KEY`** (FastAPI)
   - Used for server-to-Centrifugo API calls
   - FastAPI uses this to publish messages
   - **CRITICAL:** Must be kept secret and changed from default

### Production Secrets

**⚠️ BEFORE DEPLOYING TO PRODUCTION:**

```bash
# Generate strong secrets
SECRET_KEY=$(openssl rand -hex 32)
API_KEY=$(openssl rand -hex 32)

# Update .env
echo "CENTRIFUGO_TOKEN_SECRET=$SECRET_KEY" >> .env
echo "CENTRIFUGO_API_KEY=$API_KEY" >> .env

# Update centrifugo-config.json
# Replace:
#   "token_hmac_secret_key": "your-secret-key-change-in-production"
#   "api_key": "your-api-key-change-in-production"
# With your generated values
```

## Testing Security

Run the security audit in browser console:
```javascript
// See test_centrifugo.html or use browser dev tools
// Tests:
// 1. Unauthenticated requests to FastAPI (should fail)
// 2. Unauthenticated WebSocket to Centrifugo (should fail)
// 3. Unauthenticated API calls to Centrifugo (should fail)
// 4. Messages without auth (should fail)
```

## Token Renewal

**Manual renewal:**
```bash
curl http://localhost:8000/centrifugo/connection-token \
  -H "X-API-Key: <your_api_key>"
```

**Client implementations should:**
- Monitor token expiration (available in JWT `exp` claim)
- Refresh token before expiration (recommend at 23 hours)
- Handle token expiration gracefully (reconnect with new token)

## Threat Model

### Protected Against

✅ Unauthenticated access
✅ Token forgery
✅ Channel enumeration/unauthorized subscription
✅ Message injection without authentication
✅ Expired token reuse
✅ Cross-user channel access

### Not Protected Against (Out of Scope)

❌ Compromised API keys (secure key storage is client responsibility)
❌ Man-in-the-middle attacks on HTTP (use HTTPS/WSS in production)
❌ DDoS attacks (implement rate limiting separately)
❌ Malicious authenticated users (implement application-level moderation)

## Production Checklist

- [ ] Change `token_hmac_secret_key` from default value
- [ ] Change `api_key` from default value
- [ ] Change `admin_password` and `admin_secret`
- [ ] Use HTTPS/WSS in production (not HTTP/WS)
- [ ] Restrict `allowed_origins` to your actual domains
- [ ] Enable rate limiting (application or infrastructure level)
- [ ] Monitor failed authentication attempts
- [ ] Implement token refresh in all clients
- [ ] Set up proper secret management (AWS Secrets Manager, etc.)
- [ ] Review and test all security settings before launch

## References

- [Centrifugo JWT Authentication](https://centrifugal.dev/docs/server/authentication)
- [Centrifugo Channel Permissions](https://centrifugal.dev/docs/server/channels)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
